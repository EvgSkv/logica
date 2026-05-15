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

"""make_extension.py — Build a DuckDB extension from a Python file.

Usage:
 python3 make_extension.py script.py [-r] [-e]

Reads LOGICA_EXTENSION from the script to discover functions and aggregations.
Transpiles via tranc, generates C++ DuckDB callbacks, compiles.

 -r   Compile and run test program.
 -e   Build loadable .duckdb_extension with metadata footer.
"""

import sys
import ast
import os
import platform
import subprocess

if __name__ == '__main__' and not __package__:
 import make_aggregation as ma
else:
 from . import make_aggregation as ma


def parse_logica_extension(source):
  """Extract LOGICA_EXTENSION dict from source."""
  tree = ast.parse(source)
  for node in ast.walk(tree):
    if (isinstance(node, ast.Assign) and
      len(node.targets) == 1 and
      isinstance(node.targets[0], ast.Name) and
      node.targets[0].id == "LOGICA_EXTENSION"):
      return ast.literal_eval(node.value)
  raise ValueError("LOGICA_EXTENSION not found in source")


def parse_function_signature(source, func_name):
  """Get (param_list, return_type) for a function."""
  func_node = ma.parse_function(source, func_name)
  params = []
  for arg in func_node.args.args:
    if arg.arg == "self":
      continue
    params.append((arg.arg, ma.get_type_str(arg.annotation)))
  ret_type = ma.get_type_str(func_node.returns)
  return params, ret_type


def extract_all_functions(cpp_body, func_names):
  """Extract preamble and all named functions from transpiled C++."""
  lines = cpp_body.split("\n")
  funcs = {}
  preamble_lines = []
  current_func = None
  current_lines = []
  brace_depth = 0
  in_main = False

  for line in lines:
    if "int main()" in line:
      in_main = True
    if in_main:
      continue

    if current_func is None:
      matched = None
      for fname in sorted(func_names, key=len, reverse=True):
        if fname in line and "(" in line and not line.strip().startswith("//"):
          matched = fname
          break
      if matched:
        current_func = matched
        current_lines = [line]
        brace_depth = line.count("{") - line.count("}")
        if brace_depth <= 0 and "{" not in line:
          pass
        elif brace_depth <= 0 and "{" in line:
          funcs[current_func] = "\n".join(current_lines)
          current_func = None
          current_lines = []
      else:
        preamble_lines.append(line)
    else:
      current_lines.append(line)
      brace_depth += line.count("{") - line.count("}")
      if brace_depth <= 0:
        funcs[current_func] = "\n".join(current_lines)
        current_func = None
        current_lines = []

  return "\n".join(preamble_lines), funcs


# ---------------------------------------------------------------------------
# Scalar UDF
# ---------------------------------------------------------------------------

def _is_list_type(ptype):
  return ptype.startswith("list[") and ptype.endswith("]")


def _list_inner(ptype):
  return ptype[5:-1].strip()


def _is_struct_list(ptype):
  if not _is_list_type(ptype):
    return False
  inner = _list_inner(ptype)
  _, dbt, _ = ma.classify_type(inner)
  return dbt == "DUCKDB_TYPE_STRUCT"


def scalar_callback(func_name, params, ret_type):
  """Generate C++ scalar function callback."""
  read_lines = []
  for i, (pname, ptype) in enumerate(params):
    cpp_t, dbt, _ = ma.classify_type(ptype)
    read_lines.append(f"    auto _v{i} = duckdb_data_chunk_get_vector(input, {i});")
    if ptype == "str":
      read_lines.append(f"    auto _d{i} = (duckdb_string_t *)duckdb_vector_get_data(_v{i});")
    elif _is_struct_list(ptype):
      pass
    elif _is_list_type(ptype):
      read_lines.append(f"    auto _ld{i} = (duckdb_list_entry *)duckdb_vector_get_data(_v{i});")
      read_lines.append(f"    auto _lc{i} = duckdb_list_vector_get_child(_v{i});")
      inner = _list_inner(ptype)
      inner_cpp, _, _ = ma.classify_type(inner)
      read_lines.append(f"    auto _lcd{i} = ({inner_cpp} *)duckdb_vector_get_data(_lc{i});")
    else:
      read_lines.append(f"    auto _d{i} = ({cpp_t} *)duckdb_vector_get_data(_v{i});")

  call_args = []
  for i, (pname, ptype) in enumerate(params):
    if ptype == "str":
      call_args.append(
        f"std::string(duckdb_string_t_data(&_d{i}[i]), "
        f"duckdb_string_t_length(_d{i}[i]))")
    elif _is_struct_list(ptype):
      inner_cpp = _list_inner(ptype)
      call_args.append(f"read_list_{inner_cpp}(_v{i}, i)")
    elif _is_list_type(ptype):
      inner = _list_inner(ptype)
      inner_cpp, _, _ = ma.classify_type(inner)
      call_args.append(
        f"std::vector<{inner_cpp}>(_lcd{i} + _ld{i}[i].offset, "
        f"_lcd{i} + _ld{i}[i].offset + _ld{i}[i].length)")
    else:
      call_args.append(f"_d{i}[i]")

  cpp_ret, _, _ = ma.classify_type(ret_type)

  if _is_struct_list(ret_type):
    ret_class = _list_inner(ret_type)
    return f"""
static void {func_name}_scalar(duckdb_function_info info, duckdb_data_chunk input,
                duckdb_vector output) {{
  idx_t count = duckdb_data_chunk_get_size(input);
{chr(10).join(read_lines)}
  auto list_data = (duckdb_list_entry *)duckdb_vector_get_data(output);
  idx_t current_offset = duckdb_list_vector_get_size(output);
  for (idx_t i = 0; i < count; i++) {{
        auto _r = {func_name}({', '.join(call_args)});
        list_data[i].offset = current_offset;
        list_data[i].length = _r.size();
        duckdb_list_vector_reserve(output, current_offset + _r.size());
        auto child = duckdb_list_vector_get_child(output);
        for (size_t j = 0; j < _r.size(); j++) {{
            write_{ret_class}(child, current_offset++, _r[j]);
        }}
        duckdb_list_vector_set_size(output, current_offset);
  }}
}}
"""

  if ret_type == "str":
    write = (f"        auto _r = {func_name}({', '.join(call_args)});\n"
        f"        duckdb_vector_assign_string_element_len("
        f"output, i, _r.c_str(), _r.size());")
  else:
    write = (f"        (({cpp_ret} *)duckdb_vector_get_data(output))[i] = "
        f"{func_name}({', '.join(call_args)});")

  return f"""
static void {func_name}_scalar(duckdb_function_info info, duckdb_data_chunk input,
                duckdb_vector output) {{
  idx_t count = duckdb_data_chunk_get_size(input);
{chr(10).join(read_lines)}
  for (idx_t i = 0; i < count; i++) {{
{write}
  }}
}}
"""


def scalar_registration(func_name, params, ret_type):
  """Generate scalar registration in a scoped block."""
  lines = [f"    {{ // Register scalar {func_name}"]
  cleanup_lines = []
  for i, (pname, ptype) in enumerate(params):
    create, cleanup = ma.make_logical_type_code(ptype, f"pt{i}", "        ")
    lines.append(create)
    cleanup_lines.append(cleanup)
  ret_create, ret_cleanup = ma.make_logical_type_code(ret_type, "rt", "        ")
  lines.append(ret_create)
  cleanup_lines.append(ret_cleanup)
  lines.append(f"        auto sf = duckdb_create_scalar_function();")
  lines.append(f'        duckdb_scalar_function_set_name(sf, "{func_name}");')
  for i in range(len(params)):
    lines.append(f"        duckdb_scalar_function_add_parameter(sf, pt{i});")
  lines.append(f"        duckdb_scalar_function_set_return_type(sf, rt);")
  lines.append(f"        duckdb_scalar_function_set_function(sf, {func_name}_scalar);")
  lines.append(f"        duckdb_register_scalar_function(con, sf);")
  lines.extend(cleanup_lines)
  lines.append(f"        duckdb_destroy_scalar_function(&sf);")
  lines.append(f"    }}")
  return "\n".join(lines)


# ---------------------------------------------------------------------------
# Aggregate — prefixed callbacks for multi-function extensions
# ---------------------------------------------------------------------------

def agg_callbacks(func_name, ret_type):
  """Generate aggregate callbacks with func_name-prefixed names."""
  _, duckdb_type, is_complex = ma.classify_type(ret_type)
  class_name = ma._parse_list_type(ret_type) if duckdb_type == "DUCKDB_TYPE_LIST_STRUCT" else None
  if duckdb_type == "DUCKDB_TYPE_STRUCT":
    class_name = ret_type

  P = func_name  # prefix

  if duckdb_type == "DUCKDB_TYPE_LIST_STRUCT":
    return _agg_heap(P, f"std::vector<{class_name}>",
            f"read_list_{class_name}(vec, i)", class_name)
  elif duckdb_type == "DUCKDB_TYPE_STRUCT":
    return _agg_value(P, class_name, f"read_{class_name}(vec, i)",
             f"write_{class_name}(result, offset + i, s->value);")
  elif is_complex and duckdb_type == "DUCKDB_TYPE_VARCHAR":
    cpp_t, _, _ = ma.classify_type(ret_type)
    return _agg_heap(P, "AggValueType",
            "parse_json(duckdb_string_t_data(&((duckdb_string_t *)duckdb_vector_get_data(vec))[i]), "
            "duckdb_string_t_length(((duckdb_string_t *)duckdb_vector_get_data(vec))[i]))")
  else:
    cpp_t, _, _ = ma.classify_type(ret_type)
    return _agg_value(P, cpp_t, f"(({cpp_t} *)duckdb_vector_get_data(vec))[i]",
             f"(({cpp_t} *)duckdb_vector_get_data(result))[offset + i] = s->value;")


def _agg_value(P, vtype, read_expr, write_expr):
  return f"""
struct {P}_State {{ bool has_value; {vtype} value; }};
static idx_t {P}_size(duckdb_function_info info) {{ return sizeof({P}_State); }}
static void {P}_init(duckdb_function_info info, duckdb_aggregate_state state) {{
  auto s = reinterpret_cast<{P}_State *>(state); s->has_value = false;
}}
static void {P}_update(duckdb_function_info info, duckdb_data_chunk input,
            duckdb_aggregate_state *states) {{
  idx_t count = duckdb_data_chunk_get_size(input);
  auto vec = duckdb_data_chunk_get_vector(input, 0);
  auto validity = duckdb_vector_get_validity(vec);
  for (idx_t i = 0; i < count; i++) {{
    if (validity && !duckdb_validity_row_is_valid(validity, i)) continue;
    auto s = reinterpret_cast<{P}_State *>(states[i]);
    auto incoming = {read_expr};
    if (!s->has_value) {{ s->has_value = true; s->value = incoming; }}
    else {{ s->value = {P}(s->value, incoming); }}
  }}
}}
static void {P}_combine(duckdb_function_info info,
            duckdb_aggregate_state *source,
            duckdb_aggregate_state *target, idx_t count) {{
  for (idx_t i = 0; i < count; i++) {{
    auto src = reinterpret_cast<{P}_State *>(source[i]);
    auto tgt = reinterpret_cast<{P}_State *>(target[i]);
    if (!src->has_value) continue;
    if (!tgt->has_value) {{ *tgt = *src; }}
    else {{ tgt->value = {P}(tgt->value, src->value); }}
  }}
}}
static void {P}_finalize(duckdb_function_info info,
             duckdb_aggregate_state *states,
             duckdb_vector result, idx_t count, idx_t offset) {{
  duckdb_vector_ensure_validity_writable(result);
  auto validity = duckdb_vector_get_validity(result);
  for (idx_t i = 0; i < count; i++) {{
    auto s = reinterpret_cast<{P}_State *>(states[i]);
    if (!s->has_value) {{ duckdb_validity_set_row_invalid(validity, offset + i); }}
    else {{ {write_expr} }}
  }}
}}
"""


def _agg_heap(P, vtype, read_expr, class_name=None):
  is_list = "std::vector" in vtype
  if is_list:
    write_fn = f"write_{class_name}" if class_name else "write_struct"
    finalize_write = f"""list_data[offset + i].offset = current_offset;
      list_data[offset + i].length = s->value->size();
      duckdb_list_vector_reserve(result, current_offset + s->value->size());
      child = duckdb_list_vector_get_child(result);
      for (auto& elem : *s->value) {{ {write_fn}(child, current_offset++, elem); }}
      duckdb_list_vector_set_size(result, current_offset);"""
    extra_finalize_vars = """auto child = duckdb_list_vector_get_child(result);
  auto list_data = (duckdb_list_entry *)duckdb_vector_get_data(result);
  idx_t current_offset = duckdb_list_vector_get_size(result);"""
    null_extra = "list_data[offset + i].offset = current_offset; list_data[offset + i].length = 0;"
  else:
    finalize_write = f"""auto json = serialize_json(*s->value);
      duckdb_vector_assign_string_element_len(result, offset + i, json.c_str(), json.size());"""
    extra_finalize_vars = ""
    null_extra = ""

  return f"""
struct {P}_State {{ bool has_value; {vtype} *value; }};
static idx_t {P}_size(duckdb_function_info info) {{ return sizeof({P}_State); }}
static void {P}_init(duckdb_function_info info, duckdb_aggregate_state state) {{
  auto s = reinterpret_cast<{P}_State *>(state); s->has_value = false; s->value = nullptr;
}}
static void {P}_destroy(duckdb_aggregate_state *states, idx_t count) {{
  for (idx_t i = 0; i < count; i++) {{
    auto s = reinterpret_cast<{P}_State *>(states[i]); delete s->value; s->value = nullptr;
  }}
}}
static void {P}_update(duckdb_function_info info, duckdb_data_chunk input,
            duckdb_aggregate_state *states) {{
  idx_t count = duckdb_data_chunk_get_size(input);
  auto vec = duckdb_data_chunk_get_vector(input, 0);
  auto validity = duckdb_vector_get_validity(vec);
  for (idx_t i = 0; i < count; i++) {{
    if (validity && !duckdb_validity_row_is_valid(validity, i)) continue;
    auto s = reinterpret_cast<{P}_State *>(states[i]);
    auto incoming = {read_expr};
    if (!s->has_value) {{ s->has_value = true; s->value = new {vtype}(std::move(incoming)); }}
    else {{ *s->value = {P}(*s->value, incoming); }}
  }}
}}
static void {P}_combine(duckdb_function_info info,
            duckdb_aggregate_state *source,
            duckdb_aggregate_state *target, idx_t count) {{
  for (idx_t i = 0; i < count; i++) {{
    auto src = reinterpret_cast<{P}_State *>(source[i]);
    auto tgt = reinterpret_cast<{P}_State *>(target[i]);
    if (!src->has_value) continue;
    if (!tgt->has_value) {{ tgt->has_value = true; tgt->value = new {vtype}(*src->value); }}
    else {{ *tgt->value = {P}(*tgt->value, *src->value); }}
  }}
}}
static void {P}_finalize(duckdb_function_info info,
             duckdb_aggregate_state *states,
             duckdb_vector result, idx_t count, idx_t offset) {{
  duckdb_vector_ensure_validity_writable(result);
  auto validity = duckdb_vector_get_validity(result);
  {extra_finalize_vars}
  for (idx_t i = 0; i < count; i++) {{
    auto s = reinterpret_cast<{P}_State *>(states[i]);
    if (!s->has_value) {{ duckdb_validity_set_row_invalid(validity, offset + i); {null_extra} }}
    else {{ {finalize_write} }}
  }}
}}
"""


def agg_registration(func_name, ret_type):
  """Generate aggregate registration in a scoped block."""
  _, duckdb_type, is_complex = ma.classify_type(ret_type)
  has_destructor = (duckdb_type == "DUCKDB_TYPE_LIST_STRUCT" or
           (is_complex and duckdb_type != "DUCKDB_TYPE_STRUCT"))

  P = func_name
  lines = [f"    {{ // Register aggregate {func_name}"]

  create, cleanup = ma.make_logical_type_code(ret_type, "at", "        ")
  lines.append(create)

  lines.append(f"        auto af = duckdb_create_aggregate_function();")
  lines.append(f'        duckdb_aggregate_function_set_name(af, "{func_name}");')
  lines.append(f"        duckdb_aggregate_function_add_parameter(af, at);")
  lines.append(f"        duckdb_aggregate_function_set_return_type(af, at);")
  lines.append(f"        duckdb_aggregate_function_set_functions(af,")
  lines.append(f"            {P}_size, {P}_init, {P}_update, {P}_combine, {P}_finalize);")
  if has_destructor:
    lines.append(f"        duckdb_aggregate_function_set_destructor(af, {P}_destroy);")
  lines.append(f"        duckdb_register_aggregate_function(con, af);")
  lines.append(cleanup)
  lines.append(f"        duckdb_destroy_aggregate_function(&af);")
  lines.append(f"    }}")
  return "\n".join(lines)


# ---------------------------------------------------------------------------
# Top-level generation
# ---------------------------------------------------------------------------

def generate_extension(source, ext_config, mode):
  functions = ext_config.get("functions", [])
  aggregations = ext_config.get("aggregations", [])
  ext_name = ext_config.get("name", "logica_ext")

  cpp_body = ma.TranspileSource(source)
  all_names = functions + aggregations
  preamble, func_codes = extract_all_functions(cpp_body, all_names)

  include = ma.duckdb_include(mode, ext_name)

  parts = [f"""{include}
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include <map>
#include <algorithm>

{preamble}
"""]

  # Emit each function body once
  for fname in all_names:
    if fname in func_codes:
      parts.append(func_codes[fname])
      parts.append("")

  # Struct read/write helpers (if needed by any aggregate or scalar function)
  needed_classes = set()
  list_classes = set()
  for fname in all_names:
    params, ret_type = parse_function_signature(source, fname)
    for _, ptype in params:
      if _is_struct_list(ptype):
        cn = _list_inner(ptype)
        needed_classes.add(cn)
        list_classes.add(cn)
    _, duckdb_type, _ = ma.classify_type(ret_type)
    class_name = ma._parse_list_type(ret_type) if duckdb_type == "DUCKDB_TYPE_LIST_STRUCT" else None
    if duckdb_type == "DUCKDB_TYPE_STRUCT":
      class_name = ret_type
    if class_name:
      needed_classes.add(class_name)
      if duckdb_type == "DUCKDB_TYPE_LIST_STRUCT":
        list_classes.add(class_name)
  if needed_classes:
    parts.append(ma._all_struct_rw_code(needed_classes))
    for cn in list_classes:
      parts.append(f"""
static std::vector<{cn}> read_list_{cn}(duckdb_vector vec, idx_t i) {{
  auto list_data = (duckdb_list_entry *)duckdb_vector_get_data(vec);
  auto child = duckdb_list_vector_get_child(vec);
  std::vector<{cn}> result;
  auto entry = list_data[i];
  for (idx_t j = entry.offset; j < entry.offset + entry.length; j++) {{
    result.push_back(read_{cn}(child, j));
  }}
  return result;
}}
""")

  # JSON helpers (if needed by varchar aggregates)
  for fname in aggregations:
    _, ret_type = parse_function_signature(source, fname)
    cpp_t, duckdb_type, _ = ma.classify_type(ret_type)
    if duckdb_type == "DUCKDB_TYPE_VARCHAR" and "map" in cpp_t:
      parts.append(ma.json_helpers(cpp_t))
      break

  # Scalar callbacks
  for fname in functions:
    params, ret_type = parse_function_signature(source, fname)
    parts.append(scalar_callback(fname, params, ret_type))

  # Aggregate callbacks
  for fname in aggregations:
    _, ret_type = parse_function_signature(source, fname)
    parts.append(agg_callbacks(fname, ret_type))

  # Build all registrations
  all_regs = []
  for fname in functions:
    params, ret_type = parse_function_signature(source, fname)
    all_regs.append(scalar_registration(fname, params, ret_type))
  for fname in aggregations:
    _, ret_type = parse_function_signature(source, fname)
    all_regs.append(agg_registration(fname, ret_type))
  reg_block = "\n".join(all_regs)

  if mode == "extension":
    parts.append(f"""
DUCKDB_EXTENSION_ENTRYPOINT(duckdb_connection con, duckdb_extension_info info,
              struct duckdb_extension_access *access) {{
{reg_block}
  return true;
}}
""")
  else:
    test_queries = []
    for fname in functions:
      params, ret_type = parse_function_signature(source, fname)
      if ret_type == "str" and len(params) == 1 and params[0][1] == "str":
        test_queries.append(f"""
  if (duckdb_query(con, "SELECT {fname}('hello world')", &res) == DuckDBSuccess) {{
    auto v = duckdb_value_varchar(&res, 0, 0);
    printf("{fname}('hello world') = %s\\n", v);
    duckdb_free(v); duckdb_destroy_result(&res);
  }}""")
      elif ret_type == "float" and len(params) == 1:
        test_queries.append(f"""
  if (duckdb_query(con, "SELECT {fname}(5)", &res) == DuckDBSuccess) {{
    printf("{fname}(5) = %f\\n", duckdb_value_double(&res, 0, 0));
    duckdb_destroy_result(&res);
  }}""")

    parts.append(f"""
int main() {{
  duckdb_database db;
  duckdb_connection con;
  if (duckdb_open(nullptr, &db) == DuckDBError) {{ printf("FAIL: open\\n"); return 1; }}
  if (duckdb_connect(db, &con) == DuckDBError) {{ printf("FAIL: connect\\n"); return 1; }}
{reg_block}
  printf("Registered: {', '.join(all_names)}\\n");
  duckdb_result res;
{"".join(test_queries)}
  duckdb_disconnect(&con);
  duckdb_close(&db);
  printf("OK!\\n");
  return 0;
}}
""")

  return "\n".join(parts)


def BuildExtension(script_path, install=False):
 with open(script_path) as f:
  source = f.read()

 ext_config = parse_logica_extension(source)
 ext_name = ext_config.get(
  "name", os.path.splitext(os.path.basename(script_path))[0])
 ext_config["name"] = ext_name

 ma._classes = ma.parse_classes(source)

 code = generate_extension(source, ext_config, "extension")

 out_cpp = f"{ext_name}_ext.cpp"
 with open(out_cpp, "w") as f:
  f.write(code)

 out_bin = os.path.abspath(f"{ext_name}.duckdb_extension")
 compile_cmd = [
  "g++", "-std=c++20", "-O2", "-shared", "-fPIC",
  f"-I{ma.GetDuckdbHeaders()}",
 ]
 if platform.system() == "Darwin":
  compile_cmd += ["-undefined", "dynamic_lookup"]
 compile_cmd += ["-o", out_bin, out_cpp]
 subprocess.run(compile_cmd, check=True)
 ext_dir = os.path.expanduser("~/.logica/extensions")
 os.makedirs(ext_dir, exist_ok=True)

 ma.append_extension_metadata(out_bin, ext_name)
 os.unlink(out_cpp)
 ext_file = f"{ext_name}.duckdb_extension"
 out_l = f"{ext_name}.l"
 lines = [
  f'# Autogenerated header for Logica-DuckDB extension {ext_name}.',
  f'@Extension("{ext_name}");']
 for fname in ext_config.get("functions", []):
  params, _ = parse_function_signature(source, fname)
  args = ", ".join(p[0] for p in params)
  sql_args = ", ".join(f"{{{p[0]}}}" for p in params)
  record = ", ".join(f"{p[0]}:" for p in params)
  lines.append(f'{fname}({args}) = SqlExpr("{fname}({sql_args})", {{{record}}});')
 for fname in ext_config.get("aggregations", []):
  params, _ = parse_function_signature(source, fname)
  arg_name = params[0][0]
  lines.append(f'{fname}({arg_name}) = SqlExpr("{fname}({{{arg_name}}})", {{{arg_name}:}});')
 lines.append('')
 with open(out_l, "w") as f:
  f.write("\n".join(lines))
 print(f"\033[1mBuilt:\033[0m {out_bin}")
 print(f"\033[1mHeader:\033[0m {out_l}")
 if install:
  import shutil
  os.replace(out_bin, os.path.join(ext_dir, os.path.basename(out_bin)))
  print(f"\033[1mInstalled to:\033[0m {ext_dir}/")
 else:
  print(f"To install globally:")
  print(f"  mv {ext_file} {ext_dir}/")


def main():
  if len(sys.argv) < 2:
    print("Usage: python3 make_extension.py script.py [-r] [-e]")
    sys.exit(1)

  script_path = sys.argv[1]
  run = "-r" in sys.argv
  extension = "-e" in sys.argv

  with open(script_path) as f:
    source = f.read()

  ext_config = parse_logica_extension(source)
  functions = ext_config.get("functions", [])
  aggregations = ext_config.get("aggregations", [])
  ext_name = ext_config.get("name",
               os.path.splitext(os.path.basename(script_path))[0])

  ma._classes = ma.parse_classes(source)

  print(f"Extension: {ext_name}")
  for f in functions:
    params, ret = parse_function_signature(source, f)
    ptypes = ", ".join(t for _, t in params)
    print(f"  function {f}({ptypes}) -> {ret}")
  for f in aggregations:
    _, ret = parse_function_signature(source, f)
    print(f"  aggregation {f}({ret}, {ret}) -> {ret}")

  ext_config["name"] = ext_name
  mode = "extension" if extension else "test"
  code = generate_extension(source, ext_config, mode)

  out_cpp = f"{ext_name}_ext.cpp"
  with open(out_cpp, "w") as f:
    f.write(code)
  print(f"Generated: {out_cpp}")

  if run or extension:
    if extension:
      out_bin = os.path.abspath(f"{ext_name}.duckdb_extension")
      compile_cmd = [
        "g++", "-std=c++20", "-O2", "-shared", "-fPIC",
        f"-I{ma.GetDuckdbHeaders()}",
      ]
      if platform.system() == "Darwin":
        compile_cmd += ["-undefined", "dynamic_lookup"]
      compile_cmd += ["-o", out_bin, out_cpp]
    else:
      out_bin = f"{ext_name}_ext"
      compile_cmd = [
        "g++", "-std=c++20", "-O2",
        f"-I{ma.GetDuckdbHeaders()}",
        f"-L{ma.GetDuckdbHeaders()}",
        "-lduckdb",
        "-o", out_bin,
        out_cpp,
      ]

    print("Compiling...")
    subprocess.run(compile_cmd, check=True)

    if extension:
      ma.append_extension_metadata(out_bin, ext_name)
      print(f"Extension: {out_bin}")
      print(f"  LOAD '{out_bin}';")
    else:
      print(f"Running: ./{out_bin}")
      env = os.environ.copy()
      env["DYLD_LIBRARY_PATH"] = ma.GetDuckdbHeaders()
      subprocess.run([f"./{out_bin}"], check=True, env=env)


if __name__ == "__main__":
  main()
