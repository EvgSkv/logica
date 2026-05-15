#!/usr/bin/python
#
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""make_aggregation.py — Generate a DuckDB aggregate from a Python semigroup function.

Usage:
  python3 make_aggregation.py script.py FunctionName [-r] [-e]

The function must be a binary operation (a, b) -> c with type annotations.
Generated aggregate folds rows using this operation (semigroup, no identity).

  -r   Compile and run test program.
  -e   Build loadable .duckdb_extension for use with LOAD.
"""

import sys
import ast
import os
import subprocess
import platform


def GetDuckdbHeaders():
  path = os.environ.get("DUCKDB_HEADERS")
  if path:
    return path
  default_path = os.path.expanduser("~/.logica/duckdb_headers")
  if os.path.exists(os.path.join(default_path, "duckdb_extension.h")):
    return default_path
  import duckdb
  ver = duckdb.__version__
  plat = _detect_platform()
  if "osx" in plat:
    lib_zip = f"libduckdb-osx-universal.zip"
  elif "linux" in plat and "aarch64" in plat:
    lib_zip = f"libduckdb-linux-aarch64.zip"
  else:
    lib_zip = f"libduckdb-linux-amd64.zip"
  print("Error: DuckDB C headers not found.")
  print()
  print("To install, run:")
  print()
  print(f"  mkdir -p ~/.logica/duckdb_headers && cd ~/.logica/duckdb_headers \\")
  print(f"    && curl -LO https://github.com/duckdb/duckdb/releases/download/"
        f"v{ver}/{lib_zip} \\")
  print(f"    && unzip -o {lib_zip} && rm -f {lib_zip} \\")
  print(f"    && curl -LO https://raw.githubusercontent.com/duckdb/duckdb/"
        f"v{ver}/src/include/duckdb_extension.h")
  sys.exit(1)


def append_extension_metadata(path, ext_name):
    """Append DuckDB extension metadata footer to a compiled .duckdb_extension."""
    def pad32(s):
        b = s.encode("ascii")
        return b + b"\x00" * (32 - len(b))

    duckdb_version = "v1.2.0"  # C API version
    ext_version = "v0.1.0"
    abi_type = "C_STRUCT"
    plat = _detect_platform()

    # 8 fields x 32 bytes = 256 bytes metadata + 256 bytes signature space = 512 bytes payload
    fields = (
        pad32("")           # field8
        + pad32("")         # field7
        + pad32("")         # field6
        + pad32(abi_type)   # field5
        + pad32(ext_version)  # field4
        + pad32(duckdb_version)  # field3
        + pad32(plat)       # field2
        + pad32("4")        # field1: header signature
    )
    signature = b"\x00" * 256

    # Wasm custom section header
    header = (
        b"\x00"             # custom section type
        + b"\x93\x04"       # LEB128 length = 531
        + b"\x10"           # name length = 16
        + b"duckdb_signature"
        + b"\x80\x04"       # LEB128 payload = 512
    )

    with open(path, "ab") as f:
        f.write(header + fields + signature)


def _detect_platform():
    import duckdb
    return duckdb.execute('PRAGMA platform').fetchone()[0]


def parse_function(source, func_name):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return node
    raise ValueError(f"Function '{func_name}' not found")


def get_type_str(annotation):
    if isinstance(annotation, ast.Name):
        return annotation.id
    return ast.unparse(annotation)


def parse_classes(source):
    """Extract all class definitions: {name: [(field, type_str), ...]}."""
    tree = ast.parse(source)
    classes = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            fields = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    fields.append((item.target.id, get_type_str(item.annotation)))
            classes[node.name] = fields
    return classes


# Populated by main() after parsing source.
_classes = {}


def classify_type(py_type):
    if py_type == "int":
        return ("int64_t", "DUCKDB_TYPE_BIGINT", False)
    if py_type == "float":
        return ("double", "DUCKDB_TYPE_DOUBLE", False)
    if py_type == "str":
        return ("std::string", "DUCKDB_TYPE_VARCHAR", True)
    if py_type in ("dict[str, int]", "dict[str,int]"):
        return ("std::map<std::string, int64_t>", "DUCKDB_TYPE_VARCHAR", True)
    if py_type in ("dict[str, float]", "dict[str,float]"):
        return ("std::map<std::string, double>", "DUCKDB_TYPE_VARCHAR", True)
    if py_type in _classes:
        return (py_type, "DUCKDB_TYPE_STRUCT", True)
    m = _parse_list_type(py_type)
    if m and m in _classes:
        return (f"std::vector<{m}>", "DUCKDB_TYPE_LIST_STRUCT", True)
    if m:
        inner_cpp, inner_dbt, _ = classify_type(m)
        return (f"std::vector<{inner_cpp}>", f"DUCKDB_TYPE_LIST:{inner_dbt}", True)
    raise ValueError(f"Unsupported type: {py_type}")


def _parse_list_type(py_type):
    """Extract inner type from 'list[X]', return None if not a list type."""
    py_type = py_type.strip()
    if py_type.startswith("list[") and py_type.endswith("]"):
        return py_type[5:-1].strip()
    return None


def _topo_sort_classes():
    """Sort classes so dependencies come first."""
    visited = set()
    order = []
    def visit(name):
        if name in visited:
            return
        visited.add(name)
        for _, ftype in _classes.get(name, []):
            inner = _parse_list_type(ftype)
            dep = inner if inner else ftype
            if dep in _classes:
                visit(dep)
        order.append(name)
    for name in _classes:
        visit(name)
    return order


def TranspileSource(source):
  if __name__ == '__main__' and not __package__:
    import tranc
  else:
    from . import tranc
  return tranc.transpile(source)


def extract_function_and_preamble(cpp_body, func_name):
    lines = cpp_body.split("\n")
    func_lines = []
    preamble_lines = []
    in_func = False
    brace_depth = 0
    in_main = False

    for line in lines:
        if "int main()" in line:
            in_main = True
        if in_main:
            continue
        if not in_func and func_name in line and "(" in line:
            in_func = True
            brace_depth = line.count("{") - line.count("}")
            func_lines.append(line)
            if brace_depth <= 0 and "{" not in line:
                pass
            elif brace_depth <= 0 and "{" in line:
                in_func = False
            continue
        if in_func:
            func_lines.append(line)
            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0:
                in_func = False
            continue
        preamble_lines.append(line)

    return "\n".join(preamble_lines), "\n".join(func_lines)


def json_helpers(cpp_type):
    if cpp_type == "std::map<std::string, int64_t>":
        return r"""
using AggValueType = std::map<std::string, int64_t>;

AggValueType parse_json(const char *s, size_t len) {
    AggValueType m;
    size_t i = 0;
    auto skip = [&]() { while (i < len && (s[i]==' '||s[i]=='\t'||s[i]=='\n')) i++; };
    skip(); if (i >= len || s[i] != '{') return m; i++;
    while (i < len) {
        skip(); if (s[i] == '}') break; if (s[i] == ',') { i++; continue; }
        if (s[i] != '"') break; i++;
        std::string key;
        while (i < len && s[i] != '"') key += s[i++]; i++; skip();
        if (i < len && s[i] == ':') i++; skip();
        bool neg = false; if (i < len && s[i] == '-') { neg = true; i++; }
        int64_t val = 0;
        while (i < len && s[i] >= '0' && s[i] <= '9') { val = val*10 + (s[i]-'0'); i++; }
        if (neg) val = -val;
        m[key] = val;
    }
    return m;
}

std::string serialize_json(const AggValueType& m) {
    std::string r = "{";
    bool first = true;
    for (auto& [k, v] : m) {
        if (!first) r += ", ";
        r += "\"" + k + "\": " + std::to_string(v);
        first = false;
    }
    return r + "}";
}
"""
    if cpp_type == "std::map<std::string, double>":
        return r"""
using AggValueType = std::map<std::string, double>;

AggValueType parse_json(const char *s, size_t len) {
    AggValueType m;
    size_t i = 0;
    auto skip = [&]() { while (i < len && (s[i]==' '||s[i]=='\t'||s[i]=='\n')) i++; };
    skip(); if (i >= len || s[i] != '{') return m; i++;
    while (i < len) {
        skip(); if (s[i] == '}') break; if (s[i] == ',') { i++; continue; }
        if (s[i] != '"') break; i++;
        std::string key;
        while (i < len && s[i] != '"') key += s[i++]; i++; skip();
        if (i < len && s[i] == ':') i++; skip();
        std::string num_s;
        while (i < len && s[i] != ',' && s[i] != '}' && s[i] != ' ') { num_s += s[i]; i++; }
        m[key] = std::stod(num_s);
    }
    return m;
}

std::string serialize_json(const AggValueType& m) {
    std::string r = "{";
    bool first = true;
    for (auto& [k, v] : m) {
        if (!first) r += ", ";
        r += "\"" + k + "\": " + std::to_string(v);
        first = false;
    }
    return r + "}";
}
"""
    raise ValueError(f"No JSON helpers for {cpp_type}")


# ---------------------------------------------------------------------------
# Code generation: callbacks (shared between test and extension modes)
# ---------------------------------------------------------------------------

def duckdb_include(mode, ext_name=""):
    if mode == "extension":
        return f"""#define DUCKDB_EXTENSION_NAME {ext_name}
#include "duckdb_extension.h"
DUCKDB_EXTENSION_EXTERN"""
    return '#include "duckdb.h"'


def simple_callbacks(func_name, cpp_type, duckdb_type, preamble, func_code, mode="test"):
    cast = f"({cpp_type} *)"
    include = duckdb_include(mode, func_name.lower())
    return f"""
{include}
#include <cstdio>
#include <cstdint>
#include <cstring>

{preamble}

{func_code}

struct AggState {{
    bool has_value;
    {cpp_type} value;
}};

static idx_t agg_state_size(duckdb_function_info info) {{
    return sizeof(AggState);
}}

static void agg_state_init(duckdb_function_info info, duckdb_aggregate_state state) {{
    auto s = reinterpret_cast<AggState *>(state);
    s->has_value = false;
    s->value = 0;
}}

static void agg_update(duckdb_function_info info, duckdb_data_chunk input,
                        duckdb_aggregate_state *states) {{
    idx_t count = duckdb_data_chunk_get_size(input);
    auto vec = duckdb_data_chunk_get_vector(input, 0);
    auto data = {cast}duckdb_vector_get_data(vec);
    auto validity = duckdb_vector_get_validity(vec);
    for (idx_t i = 0; i < count; i++) {{
        if (validity && !duckdb_validity_row_is_valid(validity, i)) continue;
        auto s = reinterpret_cast<AggState *>(states[i]);
        if (!s->has_value) {{
            s->has_value = true;
            s->value = data[i];
        }} else {{
            s->value = {func_name}(s->value, data[i]);
        }}
    }}
}}

static void agg_combine(duckdb_function_info info,
                         duckdb_aggregate_state *source,
                         duckdb_aggregate_state *target, idx_t count) {{
    for (idx_t i = 0; i < count; i++) {{
        auto src = reinterpret_cast<AggState *>(source[i]);
        auto tgt = reinterpret_cast<AggState *>(target[i]);
        if (!src->has_value) continue;
        if (!tgt->has_value) {{
            *tgt = *src;
        }} else {{
            tgt->value = {func_name}(tgt->value, src->value);
        }}
    }}
}}

static void agg_finalize(duckdb_function_info info,
                          duckdb_aggregate_state *states,
                          duckdb_vector result, idx_t count, idx_t offset) {{
    auto data = {cast}duckdb_vector_get_data(result);
    duckdb_vector_ensure_validity_writable(result);
    auto validity = duckdb_vector_get_validity(result);
    for (idx_t i = 0; i < count; i++) {{
        auto s = reinterpret_cast<AggState *>(states[i]);
        if (!s->has_value) {{
            duckdb_validity_set_row_invalid(validity, offset + i);
        }} else {{
            data[offset + i] = s->value;
        }}
    }}
}}
"""


def complex_varchar_callbacks(func_name, cpp_type, duckdb_type, preamble, func_code, mode="test"):
    helpers = json_helpers(cpp_type)
    include = duckdb_include(mode, func_name.lower())
    return f"""
{include}
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <string>
#include <map>

{preamble}

{func_code}

{helpers}

struct AggState {{
    bool has_value;
    AggValueType *value;
}};

static idx_t agg_state_size(duckdb_function_info info) {{
    return sizeof(AggState);
}}

static void agg_state_init(duckdb_function_info info, duckdb_aggregate_state state) {{
    auto s = reinterpret_cast<AggState *>(state);
    s->has_value = false;
    s->value = nullptr;
}}

static void agg_destroy(duckdb_aggregate_state *states, idx_t count) {{
    for (idx_t i = 0; i < count; i++) {{
        auto s = reinterpret_cast<AggState *>(states[i]);
        delete s->value;
        s->value = nullptr;
    }}
}}

static void agg_update(duckdb_function_info info, duckdb_data_chunk input,
                        duckdb_aggregate_state *states) {{
    idx_t count = duckdb_data_chunk_get_size(input);
    auto vec = duckdb_data_chunk_get_vector(input, 0);
    auto data = (duckdb_string_t *)duckdb_vector_get_data(vec);
    auto validity = duckdb_vector_get_validity(vec);
    for (idx_t i = 0; i < count; i++) {{
        if (validity && !duckdb_validity_row_is_valid(validity, i)) continue;
        auto s = reinterpret_cast<AggState *>(states[i]);
        auto len = duckdb_string_t_length(data[i]);
        auto ptr = duckdb_string_t_data(&data[i]);
        AggValueType incoming = parse_json(ptr, len);
        if (!s->has_value) {{
            s->has_value = true;
            s->value = new AggValueType(std::move(incoming));
        }} else {{
            *s->value = {func_name}(*s->value, incoming);
        }}
    }}
}}

static void agg_combine(duckdb_function_info info,
                         duckdb_aggregate_state *source,
                         duckdb_aggregate_state *target, idx_t count) {{
    for (idx_t i = 0; i < count; i++) {{
        auto src = reinterpret_cast<AggState *>(source[i]);
        auto tgt = reinterpret_cast<AggState *>(target[i]);
        if (!src->has_value) continue;
        if (!tgt->has_value) {{
            tgt->has_value = true;
            tgt->value = new AggValueType(*src->value);
        }} else {{
            *tgt->value = {func_name}(*tgt->value, *src->value);
        }}
    }}
}}

static void agg_finalize(duckdb_function_info info,
                          duckdb_aggregate_state *states,
                          duckdb_vector result, idx_t count, idx_t offset) {{
    duckdb_vector_ensure_validity_writable(result);
    auto validity = duckdb_vector_get_validity(result);
    for (idx_t i = 0; i < count; i++) {{
        auto s = reinterpret_cast<AggState *>(states[i]);
        if (!s->has_value) {{
            duckdb_validity_set_row_invalid(validity, offset + i);
        }} else {{
            auto json = serialize_json(*s->value);
            duckdb_vector_assign_string_element_len(result, offset + i, json.c_str(), json.size());
        }}
    }}
}}
"""


def _struct_read_field(idx, fname, ftype):
    """Generate C++ code to read one struct field from a vector at index i."""
    child = f"duckdb_struct_vector_get_child(vec, {idx})"
    if ftype in ('int', 'float'):
        cpp_t, _, _ = classify_type(ftype)
        return f"    val.{fname} = (({cpp_t} *)duckdb_vector_get_data({child}))[i];"
    if ftype == 'str':
        return (f"    {{ auto _fv = {child};\n"
                f"      auto _fd = (duckdb_string_t *)duckdb_vector_get_data(_fv);\n"
                f"      val.{fname} = std::string(duckdb_string_t_data(&_fd[i]), "
                f"duckdb_string_t_length(_fd[i])); }}")
    if ftype in _classes:
        return f"    val.{fname} = read_{ftype}({child}, i);"
    inner = _parse_list_type(ftype)
    if inner:
        return _read_list_field(idx, fname, inner)
    raise ValueError(f"Unsupported field type: {ftype}")


def _read_list_field(idx, fname, inner_type):
    """Generate C++ code to read a list[X] field from a struct vector."""
    lines = [f"    {{ auto _lv{idx} = duckdb_struct_vector_get_child(vec, {idx});"]
    lines.append(f"      auto _ld{idx} = (duckdb_list_entry *)duckdb_vector_get_data(_lv{idx});")
    lines.append(f"      auto _lc{idx} = duckdb_list_vector_get_child(_lv{idx});")
    lines.append(f"      auto _le{idx} = _ld{idx}[i];")
    lines.append(f"      val.{fname}.clear();")
    lines.append(f"      for (idx_t _j = _le{idx}.offset; _j < _le{idx}.offset + _le{idx}.length; _j++) {{")
    if inner_type in _classes:
        lines.append(f"        val.{fname}.push_back(read_{inner_type}(_lc{idx}, _j));")
    elif inner_type == 'str':
        lines.append(f"        {{ auto _sd = (duckdb_string_t *)duckdb_vector_get_data(_lc{idx});")
        lines.append(f"          val.{fname}.push_back(std::string(duckdb_string_t_data(&_sd[_j]), duckdb_string_t_length(_sd[_j]))); }}")
    else:
        cpp_t, _, _ = classify_type(inner_type)
        lines.append(f"        val.{fname}.push_back((({cpp_t} *)duckdb_vector_get_data(_lc{idx}))[_j]);")
    lines.append(f"      }}")
    lines.append(f"    }}")
    return "\n".join(lines)


def _struct_write_field(idx, fname, ftype):
    """Generate C++ code to write one struct field to a vector at index i."""
    child = f"duckdb_struct_vector_get_child(vec, {idx})"
    if ftype in ('int', 'float'):
        cpp_t, _, _ = classify_type(ftype)
        return f"    (({cpp_t} *)duckdb_vector_get_data({child}))[i] = val.{fname};"
    if ftype == 'str':
        return (f"    duckdb_vector_assign_string_element_len({child}, i, "
                f"val.{fname}.c_str(), val.{fname}.size());")
    if ftype in _classes:
        return f"    write_{ftype}({child}, i, val.{fname});"
    inner = _parse_list_type(ftype)
    if inner:
        return _write_list_field(idx, fname, inner)
    raise ValueError(f"Unsupported field type: {ftype}")


def _write_list_field(idx, fname, inner_type):
    """Generate C++ code to write a list[X] field to a struct vector."""
    lines = [f"    {{ auto _lv{idx} = duckdb_struct_vector_get_child(vec, {idx});"]
    lines.append(f"      auto _ld{idx} = (duckdb_list_entry *)duckdb_vector_get_data(_lv{idx});")
    lines.append(f"      idx_t _off{idx} = duckdb_list_vector_get_size(_lv{idx});")
    lines.append(f"      _ld{idx}[i].offset = _off{idx};")
    lines.append(f"      _ld{idx}[i].length = val.{fname}.size();")
    lines.append(f"      duckdb_list_vector_reserve(_lv{idx}, _off{idx} + val.{fname}.size());")
    lines.append(f"      auto _lc{idx} = duckdb_list_vector_get_child(_lv{idx});")
    lines.append(f"      for (idx_t _j = 0; _j < (idx_t)val.{fname}.size(); _j++) {{")
    if inner_type in _classes:
        lines.append(f"        write_{inner_type}(_lc{idx}, _off{idx} + _j, val.{fname}[_j]);")
    elif inner_type == 'str':
        lines.append(f"        duckdb_vector_assign_string_element_len(_lc{idx}, _off{idx} + _j, "
                     f"val.{fname}[_j].c_str(), val.{fname}[_j].size());")
    else:
        cpp_t, _, _ = classify_type(inner_type)
        lines.append(f"        (({cpp_t} *)duckdb_vector_get_data(_lc{idx}))[_off{idx} + _j] = val.{fname}[_j];")
    lines.append(f"      }}")
    lines.append(f"      duckdb_list_vector_set_size(_lv{idx}, _off{idx} + val.{fname}.size());")
    lines.append(f"    }}")
    return "\n".join(lines)


def _struct_rw_code(class_name):
    """Generate read_ClassName / write_ClassName functions for a class."""
    fields = _classes[class_name]
    read_body = "\n".join(_struct_read_field(i, f, t) for i, (f, t) in enumerate(fields))
    write_body = "\n".join(_struct_write_field(i, f, t) for i, (f, t) in enumerate(fields))
    return f"""
static {class_name} read_{class_name}(duckdb_vector vec, idx_t i) {{
    {class_name} val;
{read_body}
    return val;
}}

static void write_{class_name}(duckdb_vector vec, idx_t i, const {class_name}& val) {{
{write_body}
}}
"""


def _all_struct_rw_code(needed=None):
    """Generate read/write code for all classes in dependency order."""
    order = _topo_sort_classes()
    if needed is not None:
        reachable = set()
        def collect(name):
            if name in reachable:
                return
            reachable.add(name)
            for _, ftype in _classes.get(name, []):
                inner = _parse_list_type(ftype)
                dep = inner if inner else ftype
                if dep in _classes:
                    collect(dep)
        for n in needed:
            collect(n)
        order = [c for c in order if c in reachable]
    return "\n".join(_struct_rw_code(c) for c in order)


def struct_callbacks(func_name, class_name, preamble, func_code, mode="test"):
    include = duckdb_include(mode, func_name.lower())
    rw = _all_struct_rw_code({class_name})

    return f"""
{include}
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

{preamble}

{func_code}

{rw}

struct AggState {{
    bool has_value;
    {class_name} value;
}};

static idx_t agg_state_size(duckdb_function_info info) {{
    return sizeof(AggState);
}}

static void agg_state_init(duckdb_function_info info, duckdb_aggregate_state state) {{
    auto s = reinterpret_cast<AggState *>(state);
    s->has_value = false;
}}

static void agg_update(duckdb_function_info info, duckdb_data_chunk input,
                        duckdb_aggregate_state *states) {{
    idx_t count = duckdb_data_chunk_get_size(input);
    auto vec = duckdb_data_chunk_get_vector(input, 0);
    auto validity = duckdb_vector_get_validity(vec);
    for (idx_t i = 0; i < count; i++) {{
        if (validity && !duckdb_validity_row_is_valid(validity, i)) continue;
        auto s = reinterpret_cast<AggState *>(states[i]);
        auto incoming = read_{class_name}(vec, i);
        if (!s->has_value) {{
            s->has_value = true;
            s->value = incoming;
        }} else {{
            s->value = {func_name}(s->value, incoming);
        }}
    }}
}}

static void agg_combine(duckdb_function_info info,
                         duckdb_aggregate_state *source,
                         duckdb_aggregate_state *target, idx_t count) {{
    for (idx_t i = 0; i < count; i++) {{
        auto src = reinterpret_cast<AggState *>(source[i]);
        auto tgt = reinterpret_cast<AggState *>(target[i]);
        if (!src->has_value) continue;
        if (!tgt->has_value) {{
            *tgt = *src;
        }} else {{
            tgt->value = {func_name}(tgt->value, src->value);
        }}
    }}
}}

static void agg_finalize(duckdb_function_info info,
                          duckdb_aggregate_state *states,
                          duckdb_vector result, idx_t count, idx_t offset) {{
    duckdb_vector_ensure_validity_writable(result);
    auto validity = duckdb_vector_get_validity(result);
    for (idx_t i = 0; i < count; i++) {{
        auto s = reinterpret_cast<AggState *>(states[i]);
        if (!s->has_value) {{
            duckdb_validity_set_row_invalid(validity, offset + i);
        }} else {{
            write_{class_name}(result, offset + i, s->value);
        }}
    }}
}}
"""


def list_struct_callbacks(func_name, class_name, preamble, func_code, mode="test"):
    include = duckdb_include(mode, func_name.lower())
    rw = _all_struct_rw_code({class_name})

    return f"""
{include}
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

{preamble}

{func_code}

{rw}

static std::vector<{class_name}> read_list_{class_name}(duckdb_vector vec, idx_t i) {{
    auto list_data = (duckdb_list_entry *)duckdb_vector_get_data(vec);
    auto child = duckdb_list_vector_get_child(vec);
    std::vector<{class_name}> result;
    auto entry = list_data[i];
    for (idx_t j = entry.offset; j < entry.offset + entry.length; j++) {{
        result.push_back(read_{class_name}(child, j));
    }}
    return result;
}}

struct AggState {{
    bool has_value;
    std::vector<{class_name}> *value;
}};

static idx_t agg_state_size(duckdb_function_info info) {{
    return sizeof(AggState);
}}

static void agg_state_init(duckdb_function_info info, duckdb_aggregate_state state) {{
    auto s = reinterpret_cast<AggState *>(state);
    s->has_value = false;
    s->value = nullptr;
}}

static void agg_destroy(duckdb_aggregate_state *states, idx_t count) {{
    for (idx_t i = 0; i < count; i++) {{
        auto s = reinterpret_cast<AggState *>(states[i]);
        delete s->value;
        s->value = nullptr;
    }}
}}

static void agg_update(duckdb_function_info info, duckdb_data_chunk input,
                        duckdb_aggregate_state *states) {{
    idx_t count = duckdb_data_chunk_get_size(input);
    auto vec = duckdb_data_chunk_get_vector(input, 0);
    auto validity = duckdb_vector_get_validity(vec);
    for (idx_t i = 0; i < count; i++) {{
        if (validity && !duckdb_validity_row_is_valid(validity, i)) continue;
        auto s = reinterpret_cast<AggState *>(states[i]);
        auto incoming = read_list_{class_name}(vec, i);
        if (!s->has_value) {{
            s->has_value = true;
            s->value = new std::vector<{class_name}>(std::move(incoming));
        }} else {{
            *s->value = {func_name}(*s->value, incoming);
        }}
    }}
}}

static void agg_combine(duckdb_function_info info,
                         duckdb_aggregate_state *source,
                         duckdb_aggregate_state *target, idx_t count) {{
    for (idx_t i = 0; i < count; i++) {{
        auto src = reinterpret_cast<AggState *>(source[i]);
        auto tgt = reinterpret_cast<AggState *>(target[i]);
        if (!src->has_value) continue;
        if (!tgt->has_value) {{
            tgt->has_value = true;
            tgt->value = new std::vector<{class_name}>(*src->value);
        }} else {{
            *tgt->value = {func_name}(*tgt->value, *src->value);
        }}
    }}
}}

static void agg_finalize(duckdb_function_info info,
                          duckdb_aggregate_state *states,
                          duckdb_vector result, idx_t count, idx_t offset) {{
    duckdb_vector_ensure_validity_writable(result);
    auto validity = duckdb_vector_get_validity(result);
    auto child = duckdb_list_vector_get_child(result);
    auto list_data = (duckdb_list_entry *)duckdb_vector_get_data(result);
    idx_t current_offset = duckdb_list_vector_get_size(result);
    for (idx_t i = 0; i < count; i++) {{
        auto s = reinterpret_cast<AggState *>(states[i]);
        if (!s->has_value) {{
            duckdb_validity_set_row_invalid(validity, offset + i);
            list_data[offset + i].offset = current_offset;
            list_data[offset + i].length = 0;
        }} else {{
            list_data[offset + i].offset = current_offset;
            list_data[offset + i].length = s->value->size();
            duckdb_list_vector_reserve(result, current_offset + s->value->size());
            child = duckdb_list_vector_get_child(result);
            for (auto& elem : *s->value) {{
                write_{class_name}(child, current_offset++, elem);
            }}
            duckdb_list_vector_set_size(result, current_offset);
        }}
    }}
}}
"""


# ---------------------------------------------------------------------------
# Registration code (shared between test and extension)
# ---------------------------------------------------------------------------

def make_logical_type_code(py_type, var_name, indent="    "):
    """Generate C++ code to create a duckdb_logical_type for any Python type.
    Returns (creation_code, cleanup_code). Handles recursive struct/list nesting."""
    if py_type in ('int', 'float', 'str'):
        _, dbt, _ = classify_type(py_type)
        create = f"{indent}auto {var_name} = duckdb_create_logical_type({dbt});"
        cleanup = f"{indent}duckdb_destroy_logical_type(&{var_name});"
        return create, cleanup
    if py_type in _classes:
        fields = _classes[py_type]
        create_lines = []
        cleanup_field_lines = []
        for idx, (fname, ftype) in enumerate(fields):
            ft_var = f"{var_name}_f{idx}"
            fc, fclean = make_logical_type_code(ftype, ft_var, indent)
            create_lines.append(fc)
            cleanup_field_lines.append(fclean)
        types_arr = ", ".join(f"{var_name}_f{i}" for i in range(len(fields)))
        names_arr = ", ".join(f'"{f}"' for f, _ in fields)
        create_lines.append(f"{indent}duckdb_logical_type {var_name}_fts[] = {{{types_arr}}};")
        create_lines.append(f'{indent}const char *{var_name}_fns[] = {{{names_arr}}};')
        create_lines.append(f"{indent}auto {var_name} = duckdb_create_struct_type({var_name}_fts, {var_name}_fns, {len(fields)});")
        create_lines.extend(cleanup_field_lines)
        cleanup = f"{indent}duckdb_destroy_logical_type(&{var_name});"
        return "\n".join(create_lines), cleanup
    inner = _parse_list_type(py_type)
    if inner:
        inner_var = f"{var_name}_inner"
        ic, iclean = make_logical_type_code(inner, inner_var, indent)
        create_lines = [ic,
                        f"{indent}auto {var_name} = duckdb_create_list_type({inner_var});",
                        iclean]
        cleanup = f"{indent}duckdb_destroy_logical_type(&{var_name});"
        return "\n".join(create_lines), cleanup
    _, dbt, _ = classify_type(py_type)
    create = f"{indent}auto {var_name} = duckdb_create_logical_type({dbt});"
    cleanup = f"{indent}duckdb_destroy_logical_type(&{var_name});"
    return create, cleanup


def struct_type_creation(class_name):
    create, _ = make_logical_type_code(class_name, "type")
    return create


def struct_type_cleanup(class_name):
    _, cleanup = make_logical_type_code(class_name, "type")
    return cleanup


def list_struct_type_creation(class_name):
    create, _ = make_logical_type_code(f"list[{class_name}]", "list_type")
    return create


def list_struct_type_cleanup(class_name):
    _, cleanup = make_logical_type_code(f"list[{class_name}]", "list_type")
    return cleanup


def registration_code(func_name, duckdb_type, is_complex, class_name=None):
    has_destructor = (duckdb_type == "DUCKDB_TYPE_LIST_STRUCT" or
                      (is_complex and duckdb_type != "DUCKDB_TYPE_STRUCT"))
    destructor = (
        "    duckdb_aggregate_function_set_destructor(func, agg_destroy);\n"
        if has_destructor else "")

    if duckdb_type == "DUCKDB_TYPE_LIST_STRUCT" and class_name:
        type_create = list_struct_type_creation(class_name)
        type_cleanup = list_struct_type_cleanup(class_name)
        reg_type = "list_type"
    elif duckdb_type == "DUCKDB_TYPE_STRUCT" and class_name:
        type_create = struct_type_creation(class_name)
        type_cleanup = struct_type_cleanup(class_name)
        reg_type = "type"
    else:
        type_create = f"    auto type = duckdb_create_logical_type({duckdb_type});"
        type_cleanup = "    duckdb_destroy_logical_type(&type);"
        reg_type = "type"

    return f"""
{type_create}
    auto func = duckdb_create_aggregate_function();
    duckdb_aggregate_function_set_name(func, "{func_name}");
    duckdb_aggregate_function_add_parameter(func, {reg_type});
    duckdb_aggregate_function_set_return_type(func, {reg_type});
    duckdb_aggregate_function_set_functions(func,
        agg_state_size, agg_state_init, agg_update, agg_combine, agg_finalize);
{destructor}    duckdb_register_aggregate_function(con, func);
{type_cleanup}
    duckdb_destroy_aggregate_function(&func);
"""


# ---------------------------------------------------------------------------
# Extension entry point
# ---------------------------------------------------------------------------

def extension_entry(func_name, duckdb_type, is_complex, class_name=None):
    reg = registration_code(func_name, duckdb_type, is_complex, class_name)
    return f"""
DUCKDB_EXTENSION_ENTRYPOINT(duckdb_connection con, duckdb_extension_info info,
                            struct duckdb_extension_access *access) {{
{reg}
    return true;
}}
"""


# ---------------------------------------------------------------------------
# Test main()
# ---------------------------------------------------------------------------

def test_main_simple(func_name, duckdb_type, is_complex, class_name=None):
    reg = registration_code(func_name, duckdb_type, is_complex, class_name)
    return f"""
int main() {{
    duckdb_database db;
    duckdb_connection con;
    if (duckdb_open(nullptr, &db) == DuckDBError) {{ printf("FAIL: open\\n"); return 1; }}
    if (duckdb_connect(db, &con) == DuckDBError) {{ printf("FAIL: connect\\n"); return 1; }}
{reg}
    printf("Registered {func_name}\\n");

    duckdb_result res;
    if (duckdb_query(con, "SELECT {func_name}(x) FROM (VALUES (1),(2),(3),(4),(5)) AS t(x)", &res) == DuckDBError) {{
        printf("FAIL: %s\\n", duckdb_result_error(&res));
        duckdb_destroy_result(&res); return 1;
    }}
    auto val = duckdb_value_int64(&res, 0, 0);
    printf("{func_name}(1..5) = %lld\\n", val);
    duckdb_destroy_result(&res);
    duckdb_disconnect(&con);
    duckdb_close(&db);
    printf("OK!\\n");
    return 0;
}}
"""


def test_main_varchar(func_name, duckdb_type, is_complex, class_name=None):
    reg = registration_code(func_name, duckdb_type, is_complex, class_name)
    return f"""
int main() {{
    duckdb_database db;
    duckdb_connection con;
    if (duckdb_open(nullptr, &db) == DuckDBError) {{ printf("FAIL: open\\n"); return 1; }}
    if (duckdb_connect(db, &con) == DuckDBError) {{ printf("FAIL: connect\\n"); return 1; }}
{reg}
    printf("Registered {func_name}\\n");

    duckdb_result res;
    const char *q = R"(
        SELECT g, {func_name}(v) FROM (VALUES
            ('a', '{{"x": 1, "y": 2}}'),
            ('a', '{{"y": 3, "z": 4}}'),
            ('b', '{{"p": 10}}'),
            ('b', '{{"p": 20, "q": 5}}')
        ) AS t(g, v) GROUP BY g ORDER BY g
    )";
    if (duckdb_query(con, q, &res) == DuckDBError) {{
        printf("FAIL: %s\\n", duckdb_result_error(&res));
        duckdb_destroy_result(&res); return 1;
    }}
    printf("Results:\\n");
    for (idx_t row = 0; row < duckdb_row_count(&res); row++) {{
        auto g = duckdb_value_varchar(&res, 0, row);
        auto v = duckdb_value_varchar(&res, 1, row);
        printf("  %s: %s\\n", g, v);
        duckdb_free(g);
        duckdb_free(v);
    }}
    duckdb_destroy_result(&res);
    duckdb_disconnect(&con);
    duckdb_close(&db);
    printf("OK!\\n");
    return 0;
}}
"""


# ---------------------------------------------------------------------------
# Top-level generation
# ---------------------------------------------------------------------------

def test_main_struct(func_name, duckdb_type, is_complex, class_name):
    reg = registration_code(func_name, duckdb_type, is_complex, class_name)
    fields = _classes[class_name]
    rows = []
    test_data = [("a", [1, 3]), ("b", [10, 30])]
    for g, base_vals in test_data:
        for base in base_vals:
            parts = [f"'{fname}': {base + idx}" for idx, (fname, _) in enumerate(fields)]
            rows.append(f"            ('{g}', {{{', '.join(parts)}}})")
    values = ",\n".join(rows)
    return f"""
int main() {{
    duckdb_database db;
    duckdb_connection con;
    if (duckdb_open(nullptr, &db) == DuckDBError) {{ printf("FAIL: open\\n"); return 1; }}
    if (duckdb_connect(db, &con) == DuckDBError) {{ printf("FAIL: connect\\n"); return 1; }}
{reg}
    printf("Registered {func_name}\\n");

    duckdb_result res;
    const char *q = R"(
        SELECT g, CAST({func_name}(v) AS VARCHAR) FROM (VALUES
{values}
        ) AS t(g, v) GROUP BY g ORDER BY g
    )";
    if (duckdb_query(con, q, &res) == DuckDBError) {{
        printf("FAIL: %s\\n", duckdb_result_error(&res));
        duckdb_destroy_result(&res); return 1;
    }}
    printf("Results:\\n");
    for (idx_t row = 0; row < duckdb_row_count(&res); row++) {{
        auto g = duckdb_value_varchar(&res, 0, row);
        auto v = duckdb_value_varchar(&res, 1, row);
        printf("  %s: %s\\n", g, v);
        duckdb_free(g);
        duckdb_free(v);
    }}
    duckdb_destroy_result(&res);
    duckdb_disconnect(&con);
    duckdb_close(&db);
    printf("OK!\\n");
    return 0;
}}
"""


def test_main_list_struct(func_name, duckdb_type, is_complex, class_name):
    reg = registration_code(func_name, duckdb_type, is_complex, class_name)
    fields = _classes[class_name]
    # Build struct literals for test data
    def make_struct(vals):
        parts = [f"'{fname}': {v}" for (fname, _), v in zip(fields, vals)]
        return "{" + ", ".join(parts) + "}"

    # Two groups, each with two rows containing lists of structs
    # For KeyValue-like: [{arg: 'x', value: 1}, {arg: 'y', value: 2}]
    is_kv = len(fields) == 2 and fields[0][1] == "str"
    if is_kv:
        rows = [
            ("a", f"[{{{q(fields[0][0])}: 'x', {q(fields[1][0])}: 1}}, {{{q(fields[0][0])}: 'y', {q(fields[1][0])}: 2}}]"),
            ("a", f"[{{{q(fields[0][0])}: 'y', {q(fields[1][0])}: 3}}, {{{q(fields[0][0])}: 'z', {q(fields[1][0])}: 4}}]"),
            ("b", f"[{{{q(fields[0][0])}: 'p', {q(fields[1][0])}: 10}}]"),
            ("b", f"[{{{q(fields[0][0])}: 'p', {q(fields[1][0])}: 20}}, {{{q(fields[0][0])}: 'q', {q(fields[1][0])}: 5}}]"),
        ]
    else:
        rows = [
            ("a", f"[{make_struct([1]*len(fields))}, {make_struct([2]*len(fields))}]"),
            ("a", f"[{make_struct([3]*len(fields))}]"),
            ("b", f"[{make_struct([10]*len(fields))}]"),
            ("b", f"[{make_struct([20]*len(fields))}]"),
        ]
    values = ",\n".join(f"            ('{g}', {v})" for g, v in rows)
    return f"""
int main() {{
    duckdb_database db;
    duckdb_connection con;
    if (duckdb_open(nullptr, &db) == DuckDBError) {{ printf("FAIL: open\\n"); return 1; }}
    if (duckdb_connect(db, &con) == DuckDBError) {{ printf("FAIL: connect\\n"); return 1; }}
{reg}
    printf("Registered {func_name}\\n");

    duckdb_result res;
    const char *q = R"(
        SELECT g, CAST({func_name}(v) AS VARCHAR) FROM (VALUES
{values}
        ) AS t(g, v) GROUP BY g ORDER BY g
    )";
    if (duckdb_query(con, q, &res) == DuckDBError) {{
        printf("FAIL: %s\\n", duckdb_result_error(&res));
        duckdb_destroy_result(&res); return 1;
    }}
    printf("Results:\\n");
    for (idx_t row = 0; row < duckdb_row_count(&res); row++) {{
        auto g = duckdb_value_varchar(&res, 0, row);
        auto v = duckdb_value_varchar(&res, 1, row);
        printf("  %s: %s\\n", g, v);
        duckdb_free(g);
        duckdb_free(v);
    }}
    duckdb_destroy_result(&res);
    duckdb_disconnect(&con);
    duckdb_close(&db);
    printf("OK!\\n");
    return 0;
}}
"""


def q(s):
    return f"'{s}'"


def generate(func_name, py_type, preamble, func_code, mode):
    cpp_type, duckdb_type, is_complex = classify_type(py_type)
    class_name = _parse_list_type(py_type) if duckdb_type == "DUCKDB_TYPE_LIST_STRUCT" else None
    if duckdb_type == "DUCKDB_TYPE_STRUCT":
        class_name = py_type

    if duckdb_type == "DUCKDB_TYPE_LIST_STRUCT":
        callbacks = list_struct_callbacks(func_name, class_name, preamble, func_code, mode)
    elif duckdb_type == "DUCKDB_TYPE_STRUCT":
        callbacks = struct_callbacks(func_name, class_name, preamble, func_code, mode)
    elif is_complex and duckdb_type == "DUCKDB_TYPE_VARCHAR":
        callbacks = complex_varchar_callbacks(func_name, cpp_type, duckdb_type, preamble, func_code, mode)
    else:
        callbacks = simple_callbacks(func_name, cpp_type, duckdb_type, preamble, func_code, mode)

    if mode == "extension":
        tail = extension_entry(func_name, duckdb_type, is_complex, class_name)
    elif duckdb_type == "DUCKDB_TYPE_LIST_STRUCT":
        tail = test_main_list_struct(func_name, duckdb_type, is_complex, class_name)
    elif duckdb_type == "DUCKDB_TYPE_STRUCT":
        tail = test_main_struct(func_name, duckdb_type, is_complex, class_name)
    elif is_complex:
        tail = test_main_varchar(func_name, duckdb_type, is_complex, class_name)
    else:
        tail = test_main_simple(func_name, duckdb_type, is_complex, class_name)

    return callbacks + tail


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 make_aggregation.py script.py FunctionName [-r] [-e]")
        sys.exit(1)

    script_path = sys.argv[1]
    func_name = sys.argv[2]
    run = "-r" in sys.argv
    extension = "-e" in sys.argv

    with open(script_path) as f:
        source = f.read()

    global _classes
    _classes = parse_classes(source)

    func_node = parse_function(source, func_name)
    ret_type = get_type_str(func_node.returns)
    cpp_type, duckdb_type, is_complex = classify_type(ret_type)
    print(f"Function: {func_name}")
    print(f"  type: ({ret_type}, {ret_type}) -> {ret_type}")
    print(f"  C++: {cpp_type}  DuckDB: {duckdb_type}")

    cpp_body = TranspileSource(source)
    preamble, func_code = extract_function_and_preamble(cpp_body, func_name)

    mode = "extension" if extension else "test"
    code = generate(func_name, ret_type, preamble, func_code, mode)

    ext_name = func_name.lower()
    out_cpp = f"{ext_name}_agg.cpp"
    with open(out_cpp, "w") as f:
        f.write(code)
    print(f"Generated: {out_cpp}")

    if run or extension:
        if extension:
            out_bin = os.path.abspath(f"{ext_name}.duckdb_extension")
            compile_cmd = [
                "g++", "-std=c++20", "-O2", "-shared", "-fPIC",
                f"-I{GetDuckdbHeaders()}",
                "-undefined", "dynamic_lookup",
                "-o", out_bin,
                out_cpp,
            ]
        else:
            out_bin = f"{ext_name}_agg"
            compile_cmd = [
                "g++", "-std=c++20", "-O2",
                f"-I{GetDuckdbHeaders()}",
                f"-L{GetDuckdbHeaders()}",
                "-lduckdb",
                "-o", out_bin,
                out_cpp,
            ]

        print(f"Compiling...")
        subprocess.run(compile_cmd, check=True)

        if extension:
            append_extension_metadata(out_bin, ext_name)
            print(f"Extension: {out_bin}")
            print(f'  LOAD \'{out_bin}\';')
        else:
            print(f"Running: ./{out_bin}")
            env = os.environ.copy()
            env["DYLD_LIBRARY_PATH"] = GetDuckdbHeaders()
            subprocess.run([f"./{out_bin}"], check=True, env=env)


if __name__ == "__main__":
    main()
