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

"""tranc.py — Python to C++ transpiler.

Usage:
  python3 tranc.py program.py              # emit C++ to stdout
  python3 tranc.py program.py -o out.cpp   # write C++ to file
  python3 tranc.py program.py -r           # compile and run
"""

import ast
import sys
import subprocess
import tempfile
import os


class TranspileError(Exception):
  def __init__(self, message, node=None):
    if node and hasattr(node, 'lineno'):
      message = f"line {node.lineno}: {message}"
    super().__init__(message)


class Transpiler:
  def __init__(self):
    self.indent = 0
    self.output_lines = []
    self.known_vars = set()
    self.var_types = {}
    self.class_names = set()
    self.function_depth = 0

  def emit(self, line):
    self.output_lines.append("  " * self.indent + line)

  def emit_blank(self):
    self.output_lines.append("")

  def result(self):
    return "\n".join(self.output_lines) + "\n"

  # --- Type inference (simple) ---

  def infer_type(self, node):
    if isinstance(node, ast.Constant):
      if isinstance(node.value, bool):
        return "TrBool"
      if isinstance(node.value, int):
        return "int64_t"
      if isinstance(node.value, float):
        return "double"
      if isinstance(node.value, str):
        return "std::string"
    if isinstance(node, ast.Name):
      return self.var_types.get(node.id)
    if isinstance(node, ast.BinOp):
      left_t = self.infer_type(node.left)
      right_t = self.infer_type(node.right)
      if isinstance(node.op, ast.Mult):
        if left_t and left_t.startswith("std::vector<"):
          return left_t
        if right_t and right_t.startswith("std::vector<"):
          return right_t
      if "double" in (left_t, right_t):
        return "double"
      if "std::string" in (left_t, right_t):
        return "std::string"
      return left_t or right_t
    if isinstance(node, ast.Call):
      if isinstance(node.func, ast.Name):
        if node.func.id == "int":
          return "int64_t"
        if node.func.id == "float":
          return "double"
        if node.func.id == "str":
          return "std::string"
        if node.func.id in self.class_names:
          return node.func.id
    if isinstance(node, ast.List):
      if node.elts:
        elem_t = self.infer_type(node.elts[0])
        if elem_t:
          return f"std::vector<{elem_t}>"
      return "std::vector<int64_t>"
    if isinstance(node, ast.Dict):
      if node.keys and node.values:
        kt = self.infer_type(node.keys[0])
        vt = self.infer_type(node.values[0])
        if kt and vt:
          return f"std::map<{kt}, {vt}>"
      return "std::map<std::string, int64_t>"
    if isinstance(node, ast.Set):
      if node.elts:
        elem_t = self.infer_type(node.elts[0])
        if elem_t:
          return f"std::unordered_set<{elem_t}>"
      return "std::unordered_set<int64_t>"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
      if node.func.id == "set":
        if node.args:
          arg_t = self.infer_type(node.args[0])
          if arg_t and arg_t.startswith("std::vector<"):
            return f"std::unordered_set<{arg_t[len('std::vector<'):-1]}>"
          if arg_t and arg_t.startswith("std::unordered_set<"):
            return arg_t
        return "std::unordered_set<int64_t>"
    return None

  # --- Expressions ---

  def expr(self, node):
    if isinstance(node, ast.Constant):
      if isinstance(node.value, bool):
        return "TrBool(true)" if node.value else "TrBool(false)"
      if isinstance(node.value, int):
        return str(node.value)
      if isinstance(node.value, float):
        return repr(node.value)
      if isinstance(node.value, str):
        escaped = (node.value
                   .replace("\\", "\\\\")
                   .replace('"', '\\"')
                   .replace("\n", "\\n")
                   .replace("\t", "\\t"))
        return f'std::string("{escaped}")'
      if node.value is None:
        return "nullptr"
      raise TranspileError(f"unsupported constant: {node.value!r}", node)

    if isinstance(node, ast.Name):
      if node.id == "self":
        return "this"
      return node.id

    if isinstance(node, ast.BinOp):
      left = self.expr(node.left)
      right = self.expr(node.right)
      op = self.binop(node.op)
      if isinstance(node.op, ast.Add):
        left_t = self.infer_type(node.left)
        if left_t == "std::string":
          return f"({left} + {right})"
      if isinstance(node.op, ast.Mult):
        left_t = self.infer_type(node.left)
        right_t = self.infer_type(node.right)
        if left_t and left_t.startswith("std::vector<"):
          return f"tranc_repeat({left}, {right})"
        if right_t and right_t.startswith("std::vector<"):
          return f"tranc_repeat({right}, {left})"
      return f"({left} {op} {right})"

    if isinstance(node, ast.UnaryOp):
      operand = self.expr(node.operand)
      if isinstance(node.op, ast.USub):
        return f"(-{operand})"
      if isinstance(node.op, ast.Not):
        return f"(!{operand})"
      raise TranspileError(f"unsupported unary op: {type(node.op).__name__}", node)

    if isinstance(node, ast.Compare):
      parts = []
      left = node.left
      for op, comparator in zip(node.ops, node.comparators):
        if isinstance(op, ast.In):
          parts.append(f"tranc_contains({self.expr(comparator)}, {self.expr(left)})")
        elif isinstance(op, ast.NotIn):
          parts.append(f"TrBool(!tranc_contains({self.expr(comparator)}, {self.expr(left)}))")
        elif isinstance(op, ast.Is):
          if isinstance(comparator, ast.Constant) and comparator.value is None:
            if isinstance(left, ast.Name) and left.id in self.var_types:
              parts.append("TrBool(false)")
            else:
              parts.append(f"TrBool({self.expr(left)} == nullptr)")
          else:
            parts.append(f"TrBool({self.expr(left)} == {self.expr(comparator)})")
        elif isinstance(op, ast.IsNot):
          if isinstance(comparator, ast.Constant) and comparator.value is None:
            if isinstance(left, ast.Name) and left.id in self.var_types:
              parts.append("TrBool(true)")
            else:
              parts.append(f"TrBool({self.expr(left)} != nullptr)")
          else:
            parts.append(f"TrBool({self.expr(left)} != {self.expr(comparator)})")
        elif isinstance(op, ast.LtE):
          left_type = None
          if isinstance(left, ast.Name) and left.id in self.var_types:
            left_type = self.var_types[left.id]
          if not left_type:
            left_type = self.infer_type(left)
          if left_type and "unordered_set" in left_type:
            parts.append(f"tranc_issubset({self.expr(left)}, {self.expr(comparator)})")
          else:
            parts.append(f"TrBool({self.expr(left)} {self.cmpop(op)} {self.expr(comparator)})")
        else:
          parts.append(f"TrBool({self.expr(left)} {self.cmpop(op)} {self.expr(comparator)})")
        left = comparator
      return " && ".join(parts) if len(parts) > 1 else parts[0]

    if isinstance(node, ast.BoolOp):
      op = " && " if isinstance(node.op, ast.And) else " || "
      parts = [self.expr(v) for v in node.values]
      return "(" + op.join(parts) + ")"

    if isinstance(node, ast.Call):
      return self.call_expr(node)

    if isinstance(node, ast.Attribute):
      obj = self.expr(node.value)
      if obj == "this":
        return f"this->{node.attr}"
      return f"{obj}.{node.attr}"

    if isinstance(node, ast.Subscript):
      obj = self.expr(node.value)
      idx = self.expr(node.slice)
      return f"{obj}[{idx}]"

    if isinstance(node, ast.List):
      elems = ", ".join(self.expr(e) for e in node.elts)
      elem_type = "int64_t"
      if node.elts:
        t = self.infer_type(node.elts[0])
        if t:
          elem_type = t
      return f"std::vector<{elem_type}>{{{elems}}}"

    if isinstance(node, ast.Dict):
      pairs = []
      kt = "std::string"
      vt = "int64_t"
      if node.keys:
        t = self.infer_type(node.keys[0])
        if t: kt = t
      if node.values:
        t = self.infer_type(node.values[0])
        if t: vt = t
      for k, v in zip(node.keys, node.values):
        pairs.append(f"{{{self.expr(k)}, {self.expr(v)}}}")
      return f"std::map<{kt}, {vt}>{{{', '.join(pairs)}}}"

    if isinstance(node, ast.Set):
      elems = ", ".join(self.expr(e) for e in node.elts)
      elem_type = "int64_t"
      if node.elts:
        t = self.infer_type(node.elts[0])
        if t:
          elem_type = t
      return f"std::unordered_set<{elem_type}>{{{elems}}}"

    if isinstance(node, ast.ListComp):
      return self.list_comp(node)

    if isinstance(node, ast.DictComp):
      return self.dict_comp(node)

    if isinstance(node, ast.SetComp):
      return self.set_comp(node)

    if isinstance(node, ast.IfExp):
      return (f"({self.expr(node.test)} ? "
              f"{self.expr(node.body)} : {self.expr(node.orelse)})")

    if isinstance(node, ast.JoinedStr):
      parts = []
      for v in node.values:
        if isinstance(v, ast.Constant):
          parts.append(self.expr(v))
        elif isinstance(v, ast.FormattedValue):
          parts.append(f"std::to_string({self.expr(v.value)})")
      return " + ".join(parts) if parts else 'std::string("")'

    if isinstance(node, ast.Lambda):
      params = ", ".join(f"auto& {a.arg}" for a in node.args.args)
      body = self.expr(node.body)
      return f"[&]({params}) {{ return {body}; }}"

    raise TranspileError(f"unsupported expression: {type(node).__name__}", node)

  def call_expr(self, node):
    func = node.func

    if isinstance(func, ast.Name) and func.id == "isinstance":
      return self.isinstance_expr(node)

    args = [self.expr(a) for a in node.args]

    if isinstance(func, ast.Name):
      name = func.id
      if name == "print":
        parts = " << \" \" << ".join(args) if args else '""'
        return f"std::cout << {parts} << std::endl"
      if name == "len":
        return f"static_cast<int64_t>({args[0]}.size())"
      if name == "int":
        return f"tranc_int({args[0]})"
      if name == "float":
        return f"static_cast<double>({args[0]})"
      if name == "str":
        return f"tranc_str({args[0]})"
      if name == "ord":
        return f"tranc_ord({args[0]})"
      if name == "chr":
        return f"std::string(1, static_cast<char>({args[0]}))"
      if name == "list":
        if not args:
          return "std::vector<int64_t>{}"
        arg_type = self.infer_type(node.args[0])
        if arg_type == "std::string":
          return f"tranc_list_from_string({args[0]})"
        if arg_type and arg_type.startswith("std::unordered_set<"):
          elem_t = arg_type[len("std::unordered_set<"):-1]
          return f"[&]() {{ auto _s = {args[0]}; return std::vector<{elem_t}>(_s.begin(), _s.end()); }}()"
        return args[0]
      if name == "set":
        if not args:
          return "std::unordered_set<int64_t>{}"
        arg_t = self.infer_type(node.args[0])
        if arg_t and arg_t.startswith("std::vector<"):
          elem_t = arg_t[len("std::vector<"):-1]
          return f"[&]() {{ auto _v = {args[0]}; return std::unordered_set<{elem_t}>(_v.begin(), _v.end()); }}()"
        return f"[&]() {{ auto _v = {args[0]}; return std::unordered_set<int64_t>(_v.begin(), _v.end()); }}()"
      if name == "dict":
        return args[0] if args else "std::map<std::string, int64_t>{}"
      if name == "sum":
        return f"tranc_sum({args[0]})"
      if name == "open":
        return f"std::ifstream({args[0]})"
      if name == "sorted":
        key_fn = None
        for kw in node.keywords:
          if kw.arg == "key":
            key_fn = self.expr(kw.value)
        if key_fn:
          return f"tranc_sorted_by({args[0]}, {key_fn})"
        return f"tranc_sorted({args[0]})"
      if name == "range":
        return f"tranc_range({', '.join(args)})"
      return f"{name}({', '.join(args)})"

    if isinstance(func, ast.Attribute):
      if (isinstance(func.value, ast.Name) and func.value.id == "csv"
          and func.attr == "reader"):
        return f"tranc_csv_read({args[0]})"
      obj = self.expr(func.value)
      method = func.attr
      if method == "append":
        return f"{obj}.push_back({args[0]})"
      if method == "add":
        return f"{obj}.insert({args[0]})"
      if method == "remove" or method == "discard":
        return f"{obj}.erase({args[0]})"
      if method == "keys":
        return f"tranc_keys({obj})"
      if method == "values":
        return f"tranc_values({obj})"
      if method == "get":
        if len(args) == 2:
          return f"({obj}.count({args[0]}) ? {obj}.at({args[0]}) : {args[1]})"
        return f"{obj}.at({args[0]})"
      if method == "update":
        return f"{obj}.insert({args[0]}.begin(), {args[0]}.end())"
      if method == "format":
        return f"tranc_format({obj}, {', '.join(args)})"
      return f"{obj}.{method}({', '.join(args)})"

    raise TranspileError(f"unsupported call: {ast.dump(func)}", node)

  ISINSTANCE_MAP = {
    "dict": "std::map",
    "list": "std::vector",
    "set": "std::unordered_set",
    "str": "std::string",
    "int": "int64_t",
    "float": "double",
    "bool": "bool",
  }

  def isinstance_expr(self, node):
    arg = node.args[0]
    type_node = node.args[1]
    var_type = None
    if isinstance(arg, ast.Name) and arg.id in self.var_types:
      var_type = self.var_types[arg.id]
    if var_type is None:
      var_type = self.infer_type(arg)
    if isinstance(type_node, ast.Tuple):
      type_names = [e.id for e in type_node.elts if isinstance(e, ast.Name)]
    elif isinstance(type_node, ast.Name):
      type_names = [type_node.id]
    else:
      raise TranspileError(f"unsupported isinstance type: {ast.dump(type_node)}", node)
    if var_type:
      for tn in type_names:
        cpp_prefix = self.ISINSTANCE_MAP.get(tn)
        if cpp_prefix and var_type.startswith(cpp_prefix):
          return "TrBool(true)"
      return "TrBool(false)"
    return f"TrBool(false) /* isinstance: unknown type for {self.expr(arg)} */"

  def binop(self, op):
    ops = {
      ast.Add: "+", ast.Sub: "-", ast.Mult: "*",
      ast.Div: "/", ast.Mod: "%", ast.FloorDiv: "/",
      ast.Pow: "**", ast.BitAnd: "&", ast.BitOr: "|",
      ast.BitXor: "^", ast.LShift: "<<", ast.RShift: ">>",
    }
    if type(op) in ops:
      return ops[type(op)]
    raise TranspileError(f"unsupported binop: {type(op).__name__}")

  def cmpop(self, op):
    ops = {
      ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<",
      ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
    }
    if type(op) in ops:
      return ops[type(op)]
    raise TranspileError(f"unsupported comparison: {type(op).__name__}")

  # --- Comprehensions ---

  def comp_iter(self, generators):
    """Generate nested for/if lines for comprehension generators."""
    lines = []
    for gen in generators:
      if isinstance(gen.target, ast.Tuple):
        names = ", ".join(self.expr(e) for e in gen.target.elts)
        if (isinstance(gen.iter, ast.Call) and
            isinstance(gen.iter.func, ast.Attribute) and
            gen.iter.func.attr == "items"):
          lines.append(f"for (auto& [{names}] : {self.expr(gen.iter.func.value)})")
        else:
          lines.append(f"for (auto& [{names}] : {self.expr(gen.iter)})")
      else:
        target = self.expr(gen.target)
        lines.append(f"for (auto& {target} : {self.expr(gen.iter)})")
      for if_clause in gen.ifs:
        lines.append(f"if ({self.expr(if_clause)})")
    return " ".join(lines)

  def comp_infer_iter_elem_type(self, gen):
    """Try to infer the element type of the iteration source."""
    it = gen.iter
    if isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range":
      return "int64_t"
    t = self.infer_type(it)
    if t and t.startswith("std::vector<") and t.endswith(">"):
      return t[len("std::vector<"):-1]
    return None

  def list_comp(self, node):
    elem_expr = self.expr(node.elt)
    elem_type = self.infer_type(node.elt)
    iters = self.comp_iter(node.generators)
    if not elem_type:
      # Fallback: use a two-pass trick — push first, deduce type from vector
      return f"[&]() {{ auto r = std::vector<int64_t>{{}}; {iters} r.push_back({elem_expr}); return r; }}()"
    return f"[&]() {{ std::vector<{elem_type}> r; {iters} r.push_back({elem_expr}); return r; }}()"

  def dict_comp(self, node):
    key_expr = self.expr(node.key)
    val_expr = self.expr(node.value)
    # Try to infer from the iteration variable types
    gen = node.generators[0]
    kt = self.infer_type(node.key)
    vt = self.infer_type(node.value)
    # If iterating over dict.items(), key is string, val from dict
    if not kt and isinstance(gen.target, ast.Tuple):
      if (isinstance(gen.iter, ast.Call) and
          isinstance(gen.iter.func, ast.Attribute) and
          gen.iter.func.attr == "items"):
        src_type = self.infer_type(gen.iter.func.value)
        if src_type and "std::map<" in src_type:
          inner = src_type[len("std::map<"):-1]
          parts = inner.split(", ", 1)
          if len(parts) == 2:
            kt, vt_src = parts
    # For simple `{w: len(w) for w in words}`, infer from iter
    if not kt and not isinstance(gen.target, ast.Tuple):
      kt = self.comp_infer_iter_elem_type(gen)
    kt = kt or "std::string"
    vt = vt or "int64_t"
    iters = self.comp_iter(node.generators)
    return f"[&]() {{ std::map<{kt}, {vt}> r; {iters} r[{key_expr}] = {val_expr}; return r; }}()"

  def set_comp(self, node):
    elem_expr = self.expr(node.elt)
    elem_type = self.infer_type(node.elt) or "int64_t"
    iters = self.comp_iter(node.generators)
    return f"[&]() {{ std::unordered_set<{elem_type}> r; {iters} r.insert({elem_expr}); return r; }}()"

  # --- Statements ---

  def stmt(self, node):
    if isinstance(node, ast.Assign):
      self.assign_stmt(node)
    elif isinstance(node, ast.AugAssign):
      target = self.expr(node.target)
      val = self.expr(node.value)
      if isinstance(node.op, ast.BitOr):
        self.emit(f"{{ const auto& _r = {val}; {target}.insert(_r.begin(), _r.end()); }}")
      else:
        op = self.binop(node.op)
        self.emit(f"{target} {op}= {val};")
    elif isinstance(node, ast.AnnAssign):
      self.ann_assign_stmt(node)
    elif isinstance(node, ast.Expr):
      self.emit(f"{self.expr(node.value)};")
    elif isinstance(node, ast.Return):
      if node.value:
        self.emit(f"return {self.expr(node.value)};")
      else:
        self.emit("return;")
    elif isinstance(node, ast.If):
      self.if_stmt(node)
    elif isinstance(node, ast.While):
      self.while_stmt(node)
    elif isinstance(node, ast.For):
      self.for_stmt(node)
    elif isinstance(node, ast.FunctionDef):
      self.function_def(node)
    elif isinstance(node, ast.ClassDef):
      self.class_def(node)
    elif isinstance(node, ast.Pass):
      pass
    elif isinstance(node, ast.Break):
      self.emit("break;")
    elif isinstance(node, ast.Continue):
      self.emit("continue;")
    elif isinstance(node, ast.Delete):
      for target in node.targets:
        if isinstance(target, ast.Subscript):
          obj = self.expr(target.value)
          idx = self.expr(target.slice)
          self.emit(f"{obj}.erase({idx});")
        else:
          raise TranspileError(f"unsupported del target", node)
    elif isinstance(node, ast.Assert):
      cond = self.expr(node.test)
      if node.msg:
        msg = self.expr(node.msg)
        self.emit(f'if (!({cond})) {{ std::cerr << "AssertionError: " << {msg} << std::endl; std::abort(); }}')
      else:
        self.emit(f'if (!({cond})) {{ std::cerr << "AssertionError" << std::endl; std::abort(); }}')
    elif isinstance(node, ast.With):
      self.with_stmt(node)
    elif isinstance(node, ast.Import):
      pass
    elif isinstance(node, ast.ImportFrom):
      pass
    else:
      raise TranspileError(f"unsupported statement: {type(node).__name__}", node)

  def with_stmt(self, node):
    item = node.items[0]
    ctx_expr = item.context_expr
    var = item.optional_vars
    if (isinstance(ctx_expr, ast.Call) and
        isinstance(ctx_expr.func, ast.Name) and
        ctx_expr.func.id == "open"):
      args = [self.expr(a) for a in ctx_expr.args]
      var_name = self.expr(var) if var else "_file"
      self.emit(f"{{ std::ifstream {var_name}({args[0]});")
      self.known_vars.add(var_name)
      self.var_types[var_name] = "std::ifstream"
      self.indent += 1
      for s in node.body:
        self.stmt(s)
      self.indent -= 1
      self.emit("}")
    else:
      raise TranspileError(f"unsupported with context", node)

  def assign_stmt(self, node):
    target = node.targets[0]
    val = self.expr(node.value)
    if isinstance(target, ast.Name):
      if target.id in self.known_vars:
        self.emit(f"{target.id} = {val};")
      else:
        self.known_vars.add(target.id)
        t = self.infer_type(node.value)
        if t:
          self.var_types[target.id] = t
          self.emit(f"{t} {target.id} = {val};")
        else:
          self.emit(f"auto {target.id} = {val};")
    elif isinstance(target, ast.Subscript):
      self.emit(f"{self.expr(target)} = {val};")
    elif isinstance(target, ast.Attribute):
      self.emit(f"{self.expr(target)} = {val};")
    elif isinstance(target, ast.Tuple):
      self.emit(f"auto [{', '.join(self.expr(e) for e in target.elts)}] = {val};")
    else:
      raise TranspileError(f"unsupported assign target: {type(target).__name__}", node)

  def ann_assign_stmt(self, node):
    target = self.expr(node.target)
    ann_type = self.annotation_type(node.annotation)
    self.known_vars.add(target)
    self.var_types[target] = ann_type
    if node.value:
      if isinstance(node.value, (ast.Dict, ast.List, ast.Set)) and not getattr(node.value, 'elts', None) and not getattr(node.value, 'keys', []):
        self.emit(f"{ann_type} {target} = {ann_type}{{}};")
      else:
        val = self.expr(node.value)
        self.emit(f"{ann_type} {target} = {val};")
    else:
      self.emit(f"{ann_type} {target};")

  def annotation_type(self, node):
    if isinstance(node, ast.Name):
      type_map = {"int": "int64_t", "float": "double",
                  "str": "std::string", "bool": "bool"}
      return type_map.get(node.id, node.id)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
      return node.value
    if isinstance(node, ast.Subscript):
      outer = node.value.id if isinstance(node.value, ast.Name) else None
      inner = self.annotation_type(node.slice)
      if outer == "list":
        return f"std::vector<{inner}>"
      if outer == "dict":
        if isinstance(node.slice, ast.Tuple) and len(node.slice.elts) == 2:
          k = self.annotation_type(node.slice.elts[0])
          v = self.annotation_type(node.slice.elts[1])
          return f"std::map<{k}, {v}>"
      if outer == "set":
        return f"std::unordered_set<{inner}>"
    return "auto"

  def if_stmt(self, node):
    saved_vars = self.known_vars.copy()
    self.emit(f"if ({self.expr(node.test)}) {{")
    self.indent += 1
    for s in node.body:
      self.stmt(s)
    self.indent -= 1
    self.known_vars = saved_vars.copy()
    if node.orelse:
      if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
        self.emit(f"}} else if ({self.expr(node.orelse[0].test)}) {{")
        self.indent += 1
        for s in node.orelse[0].body:
          self.stmt(s)
        self.indent -= 1
        self.known_vars = saved_vars.copy()
        if node.orelse[0].orelse:
          self.emit("} else {")
          self.indent += 1
          for s in node.orelse[0].orelse:
            self.stmt(s)
          self.indent -= 1
          self.known_vars = saved_vars.copy()
      else:
        self.emit("} else {")
        self.indent += 1
        for s in node.orelse:
          self.stmt(s)
        self.indent -= 1
        self.known_vars = saved_vars.copy()
    self.emit("}")

  def while_stmt(self, node):
    self.emit(f"while ({self.expr(node.test)}) {{")
    self.indent += 1
    for s in node.body:
      self.stmt(s)
    self.indent -= 1
    self.emit("}")

  def for_stmt(self, node):
    iter_expr = node.iter
    # for k, v in d.items()
    if (isinstance(node.target, ast.Tuple) and
        isinstance(iter_expr, ast.Call) and
        isinstance(iter_expr.func, ast.Attribute) and
        iter_expr.func.attr == "items"):
      names = [self.expr(e) for e in node.target.elts]
      obj = self.expr(iter_expr.func.value)
      self.emit(f"for (auto& [{', '.join(names)}] : {obj}) {{")
      for n in names:
        self.known_vars.add(n)
    elif isinstance(node.target, ast.Tuple):
      names = [self.expr(e) for e in node.target.elts]
      self.emit(f"for (auto& [{', '.join(names)}] : {self.expr(iter_expr)}) {{")
      for n in names:
        self.known_vars.add(n)
    else:
      target = self.expr(node.target)
      if (isinstance(iter_expr, ast.Call) and
          isinstance(iter_expr.func, ast.Name) and
          iter_expr.func.id == "range"):
        args = iter_expr.args
        if len(args) == 1:
          self.emit(f"for (int64_t {target} = 0; {target} < {self.expr(args[0])}; ++{target}) {{")
        elif len(args) == 2:
          self.emit(f"for (int64_t {target} = {self.expr(args[0])}; {target} < {self.expr(args[1])}; ++{target}) {{")
        elif len(args) == 3:
          self.emit(f"for (int64_t {target} = {self.expr(args[0])}; {target} < {self.expr(args[1])}; {target} += {self.expr(args[2])}) {{")
      else:
        iter_type = None
        if isinstance(iter_expr, ast.Name) and iter_expr.id in self.var_types:
          iter_type = self.var_types[iter_expr.id]
        if iter_type and ("std::map" in iter_type or "std::unordered_map" in iter_type):
          self.emit(f"for (auto& [{target}, _v_{target}] : {self.expr(iter_expr)}) {{")
        else:
          self.emit(f"for (auto& {target} : {self.expr(iter_expr)}) {{")
      self.known_vars.add(target)
    saved_vars = self.known_vars.copy()
    self.indent += 1
    for s in node.body:
      self.stmt(s)
    self.indent -= 1
    self.emit("}")
    self.known_vars = saved_vars

  # --- Functions ---

  def function_def(self, node):
    ret_type = "auto"
    if node.returns:
      ret_type = self.annotation_type(node.returns)
    params = []
    for arg in node.args.args:
      if arg.arg == "self":
        continue
      if arg.annotation:
        params.append(f"{self.annotation_type(arg.annotation)} {arg.arg}")
      else:
        params.append(f"auto {arg.arg}")
    params_str = ", ".join(params)
    self.emit_blank()
    if self.function_depth > 0:
      self.emit(f"auto {node.name} = [&]({params_str}) -> {ret_type} {{")
    else:
      self.emit(f"{ret_type} {node.name}({params_str}) {{")
    saved_vars = self.known_vars.copy()
    saved_types = self.var_types.copy()
    self.function_depth += 1
    for arg in node.args.args:
      if arg.arg != "self":
        self.known_vars.add(arg.arg)
        if arg.annotation:
          self.var_types[arg.arg] = self.annotation_type(arg.annotation)
    self.indent += 1
    for s in node.body:
      self.stmt(s)
    self.indent -= 1
    self.function_depth -= 1
    self.known_vars = saved_vars
    self.var_types = saved_types
    if self.function_depth > 0:
      self.emit("};")
    else:
      self.emit("}")

  # --- Classes ---

  def class_def(self, node):
    self.class_names.add(node.name)
    self.emit_blank()
    self.emit(f"struct {node.name} {{")
    self.indent += 1
    methods = []
    for item in node.body:
      if isinstance(item, ast.FunctionDef):
        methods.append(item)
      elif isinstance(item, ast.Assign):
        self.stmt(item)
      elif isinstance(item, ast.AnnAssign):
        self.ann_assign_stmt(item)
      elif isinstance(item, ast.Pass):
        pass
    for method in methods:
      self.function_def(method)
    self.indent -= 1
    self.emit("};")

  # --- Module ---

  def transpile(self, source):
    tree = ast.parse(source)
    self.preamble()
    has_main = False
    top_stmts = []
    for node in tree.body:
      if isinstance(node, (ast.FunctionDef, ast.ClassDef,
                           ast.Import, ast.ImportFrom)):
        self.stmt(node)
      else:
        top_stmts.append(node)
        if not has_main:
          has_main = True
    if top_stmts:
      self.emit_blank()
      self.emit("int main() {")
      self.indent += 1
      for s in top_stmts:
        self.stmt(s)
      self.emit("return 0;")
      self.indent -= 1
      self.emit("}")
    return self.result()

  def preamble(self):
    self.emit("#include <iostream>")
    self.emit("#include <string>")
    self.emit("#include <vector>")
    self.emit("#include <map>")
    self.emit("#include <cstdint>")
    self.emit("#include <set>")
    self.emit("#include <unordered_set>")
    self.emit("#include <unordered_map>")
    self.emit("#include <fstream>")
    self.emit("#include <algorithm>")
    self.emit("#include <sstream>")
    self.emit_blank()
    self.emit("// tranc runtime helpers")
    self.emit("struct TrBool {")
    self.emit("  bool v;")
    self.emit("  TrBool(bool b) : v(b) {}")
    self.emit("  operator bool() const { return v; }")
    self.emit("};")
    self.emit('inline std::ostream& operator<<(std::ostream& os, TrBool b) { return os << (b.v ? "True" : "False"); }')
    self.emit("std::vector<int64_t> tranc_range(int64_t n) {")
    self.emit("  std::vector<int64_t> r; r.reserve(n);")
    self.emit("  for (int64_t i = 0; i < n; ++i) r.push_back(i);")
    self.emit("  return r;")
    self.emit("}")
    self.emit("std::vector<int64_t> tranc_range(int64_t start, int64_t stop) {")
    self.emit("  std::vector<int64_t> r;")
    self.emit("  for (int64_t i = start; i < stop; ++i) r.push_back(i);")
    self.emit("  return r;")
    self.emit("}")
    self.emit("template<typename T>")
    self.emit("void tranc_print_elem(std::ostream& os, const T& v) { os << v; }")
    self.emit('inline void tranc_print_elem(std::ostream& os, const std::string& v) { os << "\'" << v << "\'"; }')
    self.emit("template<typename T>")
    self.emit("std::ostream& operator<<(std::ostream& os, const std::vector<T>& v) {")
    self.emit('  os << "[";')
    self.emit('  for (size_t i = 0; i < v.size(); ++i) { if (i) os << ", "; tranc_print_elem(os, v[i]); }')
    self.emit('  return os << "]";')
    self.emit("}")
    self.emit("template<typename K, typename V>")
    self.emit("std::ostream& operator<<(std::ostream& os, const std::map<K, V>& m) {")
    self.emit('  os << "{";')
    self.emit('  bool first = true;')
    self.emit('  for (auto& [k, v] : m) { if (!first) os << ", "; os << k << ": " << v; first = false; }')
    self.emit('  return os << "}";')
    self.emit("}")
    self.emit("std::vector<std::string> tranc_list_from_string(const std::string& s) {")
    self.emit("  std::vector<std::string> r;")
    self.emit("  for (char c : s) r.push_back(std::string(1, c));")
    self.emit("  return r;")
    self.emit("}")
    self.emit("template<typename T>")
    self.emit("std::vector<T> operator+(const std::vector<T>& a, const std::vector<T>& b) {")
    self.emit("  std::vector<T> r(a); r.insert(r.end(), b.begin(), b.end()); return r;")
    self.emit("}")
    self.emit("template<typename T>")
    self.emit("std::string tranc_str(const T& v) {")
    self.emit("  std::ostringstream os; os << v; return os.str();")
    self.emit("}")
    self.emit("template<typename K, typename V>")
    self.emit("TrBool tranc_contains(const std::map<K, V>& m, const K& key) {")
    self.emit("  return m.find(key) != m.end();")
    self.emit("}")
    self.emit("template<typename K, typename V>")
    self.emit("TrBool tranc_contains(const std::unordered_map<K, V>& m, const K& key) {")
    self.emit("  return m.find(key) != m.end();")
    self.emit("}")
    self.emit("template<typename T>")
    self.emit("TrBool tranc_contains(const std::vector<T>& v, const T& val) {")
    self.emit("  return std::find(v.begin(), v.end(), val) != v.end();")
    self.emit("}")
    self.emit("template<typename T, typename V>")
    self.emit("TrBool tranc_contains(const std::unordered_set<T>& s, const V& val) {")
    self.emit("  return s.count(static_cast<T>(val));")
    self.emit("}")
    self.emit("template<typename T>")
    self.emit("std::unordered_set<T> operator|(const std::unordered_set<T>& a, const std::unordered_set<T>& b) {")
    self.emit("  std::unordered_set<T> r(a); r.insert(b.begin(), b.end()); return r;")
    self.emit("}")
    self.emit("template<typename T>")
    self.emit("std::unordered_set<T> operator&(const std::unordered_set<T>& a, const std::unordered_set<T>& b) {")
    self.emit("  std::unordered_set<T> r; for (auto& x : a) if (b.count(x)) r.insert(x); return r;")
    self.emit("}")
    self.emit("template<typename T>")
    self.emit("std::unordered_set<T> operator-(const std::unordered_set<T>& a, const std::unordered_set<T>& b) {")
    self.emit("  std::unordered_set<T> r; for (auto& x : a) if (!b.count(x)) r.insert(x); return r;")
    self.emit("}")
    self.emit("template<typename T>")
    self.emit("std::vector<T> tranc_repeat(const std::vector<T>& v, int64_t n) {")
    self.emit("  std::vector<T> r; r.reserve(v.size() * n);")
    self.emit("  for (int64_t i = 0; i < n; i++) r.insert(r.end(), v.begin(), v.end());")
    self.emit("  return r;")
    self.emit("}")
    self.emit("template<typename T>")
    self.emit("TrBool tranc_issubset(const std::unordered_set<T>& a, const std::unordered_set<T>& b) {")
    self.emit("  for (auto& x : a) if (!b.count(x)) return false; return true;")
    self.emit("}")
    self.emit("template<typename T>")
    self.emit("std::ostream& operator<<(std::ostream& os, const std::unordered_set<T>& s) {")
    self.emit('  os << "{";')
    self.emit('  bool first = true;')
    self.emit('  for (auto& x : s) { if (!first) os << ", "; tranc_print_elem(os, x); first = false; }')
    self.emit('  return os << "}";')
    self.emit("}")
    self.emit("template<typename T>")
    self.emit("std::vector<T> tranc_sorted(const std::vector<T>& v) {")
    self.emit("  std::vector<T> r(v); std::sort(r.begin(), r.end()); return r;")
    self.emit("}")
    self.emit("template<typename T>")
    self.emit("std::vector<T> tranc_sorted(const std::unordered_set<T>& s) {")
    self.emit("  std::vector<T> r(s.begin(), s.end()); std::sort(r.begin(), r.end()); return r;")
    self.emit("}")
    self.emit("template<typename T, typename F>")
    self.emit("std::vector<T> tranc_sorted_by(const std::vector<T>& v, F key) {")
    self.emit("  std::vector<T> r(v); std::stable_sort(r.begin(), r.end(), [&](auto& a, auto& b) { return key(a) < key(b); }); return r;")
    self.emit("}")
    self.emit("std::vector<std::vector<std::string>> tranc_csv_read(std::ifstream& file) {")
    self.emit("  std::vector<std::vector<std::string>> rows;")
    self.emit("  std::string line;")
    self.emit("  while (std::getline(file, line)) {")
    self.emit("    if (line.empty()) continue;")
    self.emit("    std::vector<std::string> row;")
    self.emit("    std::istringstream ss(line);")
    self.emit("    std::string cell;")
    self.emit('    while (std::getline(ss, cell, \',\')) row.push_back(cell);')
    self.emit("    rows.push_back(row);")
    self.emit("  }")
    self.emit("  return rows;")
    self.emit("}")
    self.emit("template<typename K, typename V>")
    self.emit("std::vector<K> tranc_keys(const std::map<K, V>& m) {")
    self.emit("  std::vector<K> r; for (auto& [k, v] : m) r.push_back(k); return r;")
    self.emit("}")
    self.emit("inline int64_t tranc_int(const std::string& s) { return std::stoll(s); }")
    self.emit("inline int64_t tranc_int(int64_t v) { return v; }")
    self.emit("inline int64_t tranc_int(double v) { return static_cast<int64_t>(v); }")
    self.emit("inline int64_t tranc_ord(char c) { return static_cast<int64_t>(static_cast<unsigned char>(c)); }")
    self.emit("inline int64_t tranc_ord(const std::string& s) { return static_cast<int64_t>(static_cast<unsigned char>(s[0])); }")
    self.emit("template<typename T>")
    self.emit("T tranc_sum(const std::vector<T>& v) { T s = 0; for (auto& x : v) s += x; return s; }")


def transpile(source):
  t = Transpiler()
  return t.transpile(source)


def CompileTo(cpp, exe_path):
  with tempfile.NamedTemporaryFile(suffix=".cpp", mode="w", delete=False) as f:
    f.write(cpp)
    cpp_path = f.name
  try:
    subprocess.run(
      ["g++", "-std=c++20", "-O2", "-o", exe_path, cpp_path],
      check=True)
  finally:
    os.unlink(cpp_path)


def CompileAndRun(cpp):
  exe_path = tempfile.mktemp()
  try:
    CompileTo(cpp, exe_path)
    result = subprocess.run([exe_path])
    sys.exit(result.returncode)
  finally:
    if os.path.exists(exe_path):
      os.unlink(exe_path)


def main():
  import argparse
  parser = argparse.ArgumentParser(description="tranc — Python to C++ transpiler")
  parser.add_argument("input", help="Python source file")
  parser.add_argument("-o", "--output", help="output C++ file")
  parser.add_argument("-r", "--run", action="store_true",
                      help="compile and run")
  parser.add_argument("-c", "--compile", action="store_true",
                      help="compile only")
  args = parser.parse_args()

  with open(args.input) as f:
    source = f.read()

  cpp = transpile(source)

  if args.output:
    with open(args.output, "w") as f:
      f.write(cpp)

  if args.run or args.compile:
    with tempfile.NamedTemporaryFile(suffix=".cpp", mode="w", delete=False) as f:
      f.write(cpp)
      cpp_path = f.name
    if args.output and (args.compile or args.run):
      exe_path = args.output
    else:
      exe_path = cpp_path.replace(".cpp", "")
    try:
      subprocess.run(
        ["g++", "-std=c++20", "-O2", "-o", exe_path, cpp_path],
        check=True)
      if args.run:
        result = subprocess.run([exe_path])
        sys.exit(result.returncode)
    finally:
      os.unlink(cpp_path)
      if not args.compile and not args.output:
        if os.path.exists(exe_path):
          os.unlink(exe_path)
  elif not args.output:
    print(cpp)


if __name__ == "__main__":
  main()
