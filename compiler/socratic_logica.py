#!/usr/bin/python
#
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Socratic recursion: a recursive component evaluated natively.

A component whose predicates are marked @Recursive(P, mode: "socratic")
is not iterated through SQL. Its diamond rules are handed, as
conjunctive rules over integer relations, to the Socrates engine
(socrates/socrates.cpp): semi-naive evaluation, body atoms joined left
to right through indexes on the bound columns, Min=/Max= deltas being
the keys whose value improved. Input relations are exported from the
SQL engine as CSV, the stabilized relations are written back into the
portal tables, and the rest of the program runs as usual.

Mirrors the neural mode: universe compiles a SocraticPlan per socratic
@Iteration, concertina runs it through RunIterationAsPlan.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

if '.' not in __package__:
  from compiler import neural_logica
  from compiler import rule_translate
  from common import color
else:
  from ..compiler import neural_logica
  from ..compiler import rule_translate
  from ..common import color


ParsePhase = neural_logica.ParsePhase
AUX_MARKER = neural_logica.AUX_MARKER
DIAMOND_SUFFIX = neural_logica.DIAMOND_SUFFIX

AGGREGATIONS = {'Min': 'min', 'Max': 'max', 'Agg+': 'sum'}


def BuiltinFunctions():
  """Names of the engine's scalar functions, from socrates/functions.h."""
  path = os.path.join(_RepoRoot(), 'socrates', 'functions.h')
  with open(path) as f:
    return set(re.findall(r'^\s*FN\("([^"]+)"', f.read(), re.M))


OPERATORS = None  # filled on first use (the repo root is known then)


class SocraticCompileException(rule_translate.RuleCompileException):
  pass


def Error(message, context):
  raise SocraticCompileException(message, context)


# ============================ Build & load ==============================

def _RepoRoot():
  return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _CacheDir():
  root = os.environ.get('XDG_CACHE_HOME')
  root = (os.path.join(os.path.abspath(os.path.expanduser(root)), 'logica')
          if root else os.path.join(os.path.expanduser('~'), '.cache', 'logica'))
  digest = hashlib.sha256(_RepoRoot().encode('utf-8')).hexdigest()[:12]
  return os.path.join(root, 'socrates', digest)


def _OpenMpFlags():
  """Compiler flags for OpenMP where available (Homebrew libomp on macOS)."""
  for prefix in ['/opt/homebrew/opt/libomp', '/usr/local/opt/libomp']:
    if os.path.isfile(os.path.join(prefix, 'include', 'omp.h')):
      return (['-Xpreprocessor', '-fopenmp', '-I' + os.path.join(prefix, 'include')],
              ['-L' + os.path.join(prefix, 'lib'), '-lomp'])
  if os.uname().sysname == 'Linux':
    return ['-fopenmp'], ['-fopenmp']
  return [], []


_LIB = None


def LoadLibrary():
  """Builds the socrates executable on first use (or when the source is
  newer). The engine runs as a separate process: an error (or a crash)
  of the engine is an exception here, not the end of the notebook
  kernel."""
  global _LIB
  if _LIB is not None:
    return _LIB
  src = os.path.join(_RepoRoot(), 'socrates', 'socrates.cpp')
  header = os.path.join(_RepoRoot(), 'socrates', 'functions.h')
  cache = _CacheDir()
  try:
    os.makedirs(cache, exist_ok=True)
  except OSError:
    cache = os.path.join(tempfile.gettempdir(), 'logica_socrates')
    os.makedirs(cache, exist_ok=True)
  so = os.path.join(cache, 'socrates')
  if (not os.path.isfile(so) or
      os.path.getmtime(so) < max(os.path.getmtime(src),
                                 os.path.getmtime(header))):
    cflags, ldflags = _OpenMpFlags()
    tmp = so + '.tmp.%d' % os.getpid()
    cmd = (['c++', '-O3', '-std=c++17'] + cflags + ['-o', tmp, src] + ldflags)
    try:
      subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
      raise RuntimeError('Failed to build Socrates engine: %s' % e)
    os.replace(tmp, so)
  _LIB = so
  return so


# ============================= Compilation ==============================

def IterationIsSocratic(args):
  return bool(args.get('socratic'))


def CompilePlans(program):
  """A SocraticPlan for every @Iteration marked socratic: true."""
  plans = {}
  iteration_annotations = program.annotations.annotations.get(
      '@Iteration', {})
  for name, iteration in program.annotations.Iterations().items():
    if IterationIsSocratic(iteration_annotations.get(name, {})):
      plans[name] = SocraticPlan(program, name, iteration)
  return plans


def ExprVariables(node):
  """Variables of a compiled expression."""
  if isinstance(node, dict):
    if 'var' in node:
      return {node['var']}
    return set().union(*[ExprVariables(v) for v in node.values()])
  if isinstance(node, list):
    return set().union(*[ExprVariables(v) for v in node])
  return set()


def IsVariable(node):
  return isinstance(node, dict) and 'variable' in node


def VariableName(node):
  return node['variable']['var_name']


def IsFileTable(name):
  return name.startswith('`("') and name.endswith('")`')


class Member(object):
  """A recursive predicate of the component."""

  def __init__(self, name, diamond_name, portal, table):
    self.name = name
    self.diamond_name = diamond_name
    self.portal = portal
    self.table = table
    self.arity = 0
    self.fields = []         # key fields in column order (positions, then names)
    self.has_value = False
    self.agg = 'or'
    self.functional = False
    self.internal = False    # a hoisted aggregating expression: not written out
    self.stop = False        # a stop predicate: a row ends the run


class SocraticPlan(object):
  """Native plan of one socratic iteration."""

  def __init__(self, program, iteration_name, iteration):
    self.program = program
    self.name = iteration_name
    self.engine = program.annotations.Engine()
    self.repetitions = int(iteration['repetitions'])
    self.members = []
    self.member_of_portal = {}
    self.abstract = None     # undefined input: the plan must never run
    self.strings = set()     # string literals of the rules
    self.inputs = {}         # relation name -> table exported at run time
    self.input_fields = {}   # relation name -> key fields in column order
    self.file_inputs = {}    # relation name -> (path, width) read directly
    self.rules = []
    self.written_tables = {}
    self.allocator = rule_translate.NamesAllocator()
    # A stop predicate is a hand-written convergence test for the SQL
    # path; the engine detects its own fixpoint (and epsilon), so the
    # stop is neither compiled nor consulted (its table stays empty).
    stops = set()
    for member_args in program.annotations.annotations.get(
        '@Recursive', {}).values():
      stop = member_args.get('stop')
      if member_args.get('mode') == 'socratic' and isinstance(stop, dict):
        stops.add(stop['predicate_name'])
    for diamond_name in iteration['predicates']:
      base, phase, family = ParsePhase(diamond_name)
      if phase != 'diamond':
        continue  # X_before / X_fixpoint are SQL scaffolding, unused here.
      ground = program.annotations.Ground(diamond_name)
      assert ground, 'Diamond predicates are always grounded.'
      member = Member(base + family, diamond_name, base + '_portal' + family,
                      ground.table_name)
      member.stop = base in stops
      self.members.append(member)
      self.member_of_portal[member.portal] = member
    if not self.members:
      Error('Socratic iteration %s has no recursive members.' % self.name,
            self.name)
    self.combines = 0
    for member in list(self.members):
      self.CompileMember(member)  # may insert hoisted members before it
    for member in self.members:
      member.fields = sorted(member.fields, key=lambda f: (isinstance(f, str), f))
      if member.functional:
        member.fields.append('logica_value')
      member.arity = len(member.fields)
    self.members.sort(key=lambda m: m.stop)
    # Rules were compiled with field names; map them to columns now.
    for rule in self.rules:
      self.PlaceColumns(rule)
    # Every aggregate propagates changes the same way: a round applies all
    # pending changes, @Recursive(P, N) bounds the number of rounds, and
    # a sum change below epsilon stops propagating.
    self.epsilon = 1e-12
    for member_args in program.annotations.annotations.get(
        '@Recursive', {}).values():
      if member_args.get('mode') == 'socratic' and 'epsilon' in member_args:
        self.epsilon = float(member_args['epsilon'])

  def IsStringColumn(self, predicate_name, field):
    """Whether the inferred type of a predicate's field is a string."""
    from type_inference.research import reference_algebra
    signature = self.program.predicate_signatures.get(predicate_name, {})
    if field not in signature:
      return False
    rendered = reference_algebra.RenderType(
        reference_algebra.VeryConcreteType(signature[field]))
    return rendered == 'Str'

  def Rules(self, predicate_name):
    return [r for name, r in self.program.rules if name == predicate_name]

  def Structure(self, rule):
    return neural_logica.ExtractStructure(self.program, rule, self.allocator)

  def CompileMember(self, member):
    rules = self.Rules(member.diamond_name)
    if not rules:
      Error('Recursive predicate %s has no rules.' % color.Warn(member.name),
            member.name)
    for rule in rules:
      rs = self.Structure(rule)
      keys = [k for k in rs.select if k != 'logica_value']
      member.arity = max(member.arity, len(keys))
      for k in keys:
        if k not in member.fields:
          member.fields.append(k)
      value = rs.select.get('logica_value')
      if value is not None:
        member.has_value = True
        if (isinstance(value, dict) and 'call' in value and
            value['call']['predicate_name'] in AGGREGATIONS):
          member.agg = AGGREGATIONS[value['call']['predicate_name']]
        else:
          # A functional (=) definition is a set of rows in the SQL path
          # (several rules may give several values; aggregation, if any,
          # happens in the readers): the value is one more key column.
          member.functional = True
          member.has_value = False
      aux = [p for p in rs.tables.values() if AUX_MARKER in p]
      if aux and len(rs.tables) == 1:
        [aux_name] = set(aux)
        for aux_rule in self.Rules(aux_name):
          self.rules.append(self.CompileRule(member, self.Structure(aux_rule)))
      else:
        self.rules.append(self.CompileRule(member, rs, aggregated=value))

  def RelationName(self, table):
    """Portals of members are the state relations; everything else is
    an input read from its grounded table."""
    if table in self.member_of_portal:
      return self.member_of_portal[table].name
    if table in self.inputs or table in self.file_inputs:
      return table
    if IsFileTable(table):
      # An inlined file read: the engine parses the file itself.
      self.file_inputs[table] = (table[3:-3], None)
      return table
    ground = self.program.annotations.Ground(table)
    if ground:
      self.inputs[table] = ground.table_name
      return table
    file_read = neural_logica.PlainFileRead(self.Rules(table))
    if file_read:
      self.file_inputs[table] = file_read
      return table
    if not self.Rules(table):
      # An undefined input (a functor parameter such as R in
      # Closure(R: Parent)): this copy of the component is abstract and
      # never runs; its functor instantiations get their own plans.
      self.abstract = table
      self.inputs[table] = table
      return table
    Error('Socratic recursion reads %s, which is not a table; it must '
          'be grounded (@Ground(%s)).' % (color.Warn(table), table), table)

  def CompileCombine(self, member, crule, outer_vars, context):
    """Hoists an aggregating expression of a rule body into a member
    keyed by the outer variables it mentions: the rule then reads it
    through a left atom (null when the key has no row). When the keys
    are not bound by the expression's own body, a demand member lists
    the keys the rule asks for."""
    n = self.combines
    self.combines += 1
    crs = rule_translate.ExtractRuleStructure(
        crule, self.allocator, {v: v for v in outer_vars})
    crs.ElliminateInternalVariables(assert_full_ellimination=False)
    self.program.RunInjections(crs, self.allocator)
    crs.ElliminateInternalVariables(assert_full_ellimination=False)
    value = crs.select['logica_value']
    op = (value['call']['predicate_name']
          if isinstance(value, dict) and 'call' in value else None)
    if op not in AGGREGATIONS:
      Error('Socratic recursion does not support aggregating expression '
            '%s.' % color.Warn(op or neural_logica.ExpressionText(value)),
            context)
    mentioned = set(crs.vars_map.values())
    for u in crs.vars_unification:
      mentioned |= rule_translate.AllMentionedVariables(u, True)
    mentioned |= rule_translate.AllMentionedVariables(crs.constraints, True)
    mentioned |= rule_translate.AllMentionedVariables(value, True)
    keys = sorted(v for v in mentioned if v in outer_vars)
    aux = Member('aux%d_%s' % (n, member.name), None, None, None)
    aux.internal = True
    aux.fields = list(keys)
    aux.has_value = True
    aux.agg = AGGREGATIONS[op]
    rule = self.CompileRule(aux, crs, aggregated=value, head_keys=keys)
    # Keys the expression's own atoms do not bind are asked for: a demand
    # member lists them (the key domain is then the rule's, not the
    # expression's).
    bound = set(v['var'] for a in rule['atoms'] for v in a['fields'].values())
    demand = None
    if not set(k['var'] for k in rule['key_fields'].values()) <= bound:
      demand = Member('dem%d_%s' % (n, member.name), None, None, None)
      demand.internal = True
      demand.fields = list(keys)
      rule['atoms'].append({'rel': demand.name, 'fields': dict(rule['key_fields'])})
    self.rules.append(rule)
    at = self.members.index(member)
    for m in [demand, aux]:
      if m is not None:
        self.members.insert(at, m)
        at += 1
    return aux, demand, keys

  def CompileRule(self, member, rs, aggregated=None, head_keys=None):
    """RuleStructure -> conjunctive rule of the engine."""
    context = rs.full_rule_text or member.name
    # Variables unified through `=` collapse into one engine variable.
    union = neural_logica.UnionFind()
    for u in rs.vars_unification:
      if IsVariable(u['left']) and IsVariable(u['right']):
        union.Union(VariableName(u['left']), VariableName(u['right']))
    for (alias, field), var in rs.vars_map.items():
      if alias is not None and rs.tables[alias] == '=':
        pass
    canonical = union.Find
    outer_vars = set(rs.vars_map.values())
    for u in rs.vars_unification:
      outer_vars |= rule_translate.AllMentionedVariables(u)
    outer_vars |= rule_translate.AllMentionedVariables(rs.constraints)
    outer_vars |= rule_translate.AllMentionedVariables(rs.select)
    left_atoms = []   # (atom, demand member)

    def Expr(node):
      if IsVariable(node):
        return {'var': canonical(VariableName(node))}
      if isinstance(node, dict) and 'combine' in node:
        aux, demand, keys = self.CompileCombine(
            member, node['combine'], outer_vars, context)
        cv = 'socr_cv%d' % (self.combines - 1)
        fields = {k: {'var': canonical(k)} for k in keys}
        fields['logica_value'] = {'var': cv}
        left_atoms.append(({'rel': aux.name, 'fields': fields, 'left': True},
                           demand))
        return {'var': cv}
      if isinstance(node, dict) and 'literal' in node:
        literal = node['literal']
        if 'the_number' in literal:
          return {'const': float(literal['the_number']['number'])}
        if 'the_bool' in literal:
          return {'const': 1 if literal['the_bool']['value'] else 0}
        if 'the_string' in literal:
          # Encoded through the string dictionary at run time.
          value = literal['the_string']['the_string']
          self.strings.add(value)
          return {'str': value}
        Error('Socratic recursion supports only number and string literals.',
              context)
      if isinstance(node, dict) and 'call' in node:
        call = node['call']
        op = call['predicate_name']
        args = [fv['value']['expression']
                for fv in call['record']['field_value']]
        global OPERATORS
        if OPERATORS is None:
          OPERATORS = BuiltinFunctions()
        if op in OPERATORS:
          return {'op': op, 'args': [Expr(a) for a in args]}
        if op == '~' and len(args) == 2:
          return {'const': 1}  # a type assertion: always holds
        if (op == 'is' and len(args) == 2 and
            'literal' in args[1] and 'the_null' in args[1]['literal']):
          return {'op': 'IsNull', 'args': [Expr(args[0])]}
      if isinstance(node, dict) and 'implication' in node:
        # if c then y else z: nested Ifs.
        result = Expr(node['implication']['otherwise'])
        for branch in reversed(node['implication']['if_then']):
          result = {'op': 'If', 'args': [Expr(branch['condition']),
                                         Expr(branch['consequence']), result]}
        return result
        Error('Socratic recursion does not support %s in expressions.' %
              color.Warn(op), context)
      if isinstance(node, dict) and 'expression' in node:
        return Expr(node['expression'])
      Error('Socratic recursion cannot evaluate expression %s.' %
            neural_logica.ExpressionText(node), context)

    atoms = []
    for alias, table in rs.tables.items():
      if table == '=':
        continue
      relation = self.RelationName(table)
      fields = {field: var for (a, field), var in rs.vars_map.items()
                if a == alias}
      if IsFileTable(table):
        # File columns are named column0, column1, ...: positions.
        renamed = {}
        for field, var in fields.items():
          if not (isinstance(field, str) and field.startswith('column') and
                  field[6:].isdigit()):
            Error('Socratic recursion reads file column %s; only column0, '
                  'column1, ... are supported.' % color.Warn(str(field)),
                  context)
          renamed[int(field[6:])] = var
        fields = renamed
        known = self.input_fields.setdefault(table, [])
        for f in sorted(renamed):
          if f not in known:
            known.append(f)
        known.sort()
      atoms.append({'rel': relation,
                    'fields': {f: {'var': canonical(var)} for f, var in fields.items()}})
    # Equalities between an expression and a variable bind the variable
    # (lets); other equalities and the constraints are conditions.
    lets, conds = [], []
    for u in rs.vars_unification:
      left, right = u['left'], u['right']
      if IsVariable(left) and IsVariable(right):
        continue  # Merged by union-find.
      if IsVariable(left):
        lets.append({'var': Expr(left), 'expr': Expr(right)})
      elif IsVariable(right):
        lets.append({'var': Expr(right), 'expr': Expr(left)})
      else:
        conds.append({'op': '==', 'args': [Expr(left), Expr(right)]})
    for c in rs.constraints:
      conds.append(Expr(c))
    if head_keys is not None:
      keys = {k: {'var': canonical(k)} for k in head_keys}
    else:
      keys = {k: Expr(v) for k, v in rs.select.items() if k != 'logica_value'}
    value = None
    if member.functional:
      keys['logica_value'] = Expr(rs.select['logica_value'])
    if member.has_value:
      if (aggregated is not None and isinstance(aggregated, dict) and
          'call' in aggregated and
          aggregated['call']['predicate_name'] in AGGREGATIONS):
        value = Expr(neural_logica.FieldValues(aggregated['call'])[0])
      elif aggregated is not None:
        value = Expr(aggregated)
      else:
        value = Expr(rs.select['logica_value'])
    if left_atoms:
      # Variables computed from the expressions' values: a demand member
      # cannot depend on them.
      dependent = set(a['fields']['logica_value']['var'] for a, d in left_atoms)
      changed = True
      while changed:
        changed = False
        for l in lets:
          if l['var']['var'] not in dependent and (
              dependent & ExprVariables(l['expr'])):
            dependent.add(l['var']['var'])
            changed = True
      for atom, demand in left_atoms:
        if demand is None:
          continue
        demand_keys = {k: v for k, v in atom['fields'].items()
                       if k != 'logica_value'}
        if dependent & set(v['var'] for v in demand_keys.values()):
          Error('An aggregating expression of %s depends on another '
                'aggregating expression.' % color.Warn(member.name), context)
        self.rules.append({
            'head': demand.name, 'key_fields': demand_keys, 'values': [],
            'atoms': [dict(a) for a in atoms],
            'conds': [c for c in conds if not dependent & ExprVariables(c)],
            'lets': [l for l in lets
                     if l['var']['var'] not in dependent and
                     not dependent & ExprVariables(l['expr'])]})
      atoms.extend(atom for atom, demand in left_atoms)
    return {'head': member.name, 'key_fields': keys,
            'values': [value] if value is not None else [],
            'atoms': atoms, 'conds': conds, 'lets': lets}

  def ColumnsOf(self, relation):
    """Field -> column of a relation: a member's declared order, or for an
    input the positional fields then the named ones, value last."""
    if relation in self.member_of_portal.values() or relation in [m.name for m in self.members]:
      member = next(m for m in self.members if m.name == relation)
      return {f: i for i, f in enumerate(member.fields)}
    fields = self.input_fields.setdefault(relation, [])
    return {f: i for i, f in enumerate(fields)}

  def PlaceColumns(self, rule):
    """Turns field names of a compiled rule into column positions."""
    member = next(m for m in self.members if m.name == rule['head'])
    columns = self.ColumnsOf(member.name)
    rule['keys'] = [None] * member.arity
    for f, expr in rule.pop('key_fields').items():
      rule['keys'][columns[f]] = expr
    if any(k is None for k in rule['keys']):
      Error('A rule of %s does not bind every column: %s' % (
          color.Warn(member.name), member.fields), member.name)
    for atom in rule['atoms']:
      fields = atom.pop('fields')
      rel = atom['rel']
      if rel in [m.name for m in self.members]:
        columns = self.ColumnsOf(rel)
        m = next(mm for mm in self.members if mm.name == rel)
        has_value = 'logica_value' in fields and m.has_value
        width = m.arity
      else:
        # Inputs: columns in the order their fields are first seen,
        # positional ones first; the value column, if any, last.
        known = self.input_fields.setdefault(rel, [])
        for f in sorted(fields, key=lambda f: (isinstance(f, str), f)):
          if f != 'logica_value' and f not in known:
            known.append(f)
        columns = {f: i for i, f in enumerate(known)}
        has_value = 'logica_value' in fields
        width = len(known)
      args = [None] * width
      for f, expr in fields.items():
        if f == 'logica_value' and (rel not in [m.name for m in self.members] or m.has_value):
          continue
        args[columns[f]] = expr
      if has_value:
        args.append(fields['logica_value'])
      atom['args'] = args
      atom['has_value'] = has_value
      atom['width'] = width

  # ============================== Run ===================================

  def Query(self, sql_runner, sql):
    """(header, rows) of a query: terminal runners return the pair,
    notebook runners a DataFrame."""
    result = sql_runner(sql, self.engine, is_final=True)
    if isinstance(result, tuple):
      header, rows = result
      return list(header), [list(r) for r in rows]
    return list(result.columns), result.values.tolist()

  def Columns(self, sql_runner, table, types=False):
    if types:
      unused, rows = self.Query(sql_runner, 'DESCRIBE %s' % table)
      return [(r[0], r[1]) for r in rows]
    header, unused_rows = self.Query(sql_runner,
                                     'SELECT * FROM %s LIMIT 0' % table)
    return header

  def Run(self, sql_runner, progress=None):
    import time
    if self.abstract:
      Error('Socratic recursion of %s reads %s, which is not defined.' % (
          self.name, color.Warn(self.abstract)), self.name)
    verbose = os.environ.get('SOCRATES_VERBOSE', '').lower() not in ('', '0', 'false')
    timings = {}
    t = time.monotonic()
    lib = LoadLibrary()
    timings['build'] = time.monotonic() - t
    t = time.monotonic()
    workdir = tempfile.mkdtemp(prefix='socrates_')
    relations = {}
    # Strings travel as dictionary ids: one dictionary of every string
    # column of the inputs plus the literals of the rules.
    string_columns = {}  # table -> [column]
    for relation, table in self.inputs.items():
      for c in self.Columns(sql_runner, table, types=True):
        if c[1] == 'VARCHAR':
          string_columns.setdefault(table, []).append(c[0])
    dictionary = None
    if string_columns or self.strings:
      dictionary = 'socrates_dict_' + self.name
      parts = ['SELECT %s AS s FROM %s' % (c, t)
               for t, cs in string_columns.items() for c in cs]
      parts += ["SELECT '%s' AS s" % v.replace("'", "''") for v in sorted(self.strings)]
      sql_runner(
          "CREATE OR REPLACE TABLE %s AS SELECT row_number() OVER (ORDER BY s) "
          "AS id, s FROM (SELECT DISTINCT s FROM (%s) WHERE s IS NOT NULL)" % (
              dictionary, ' UNION ALL '.join(parts)), self.engine, is_final=False)
      ids = {}
      if self.strings:
        unused, rows = self.Query(sql_runner, 'SELECT s, id FROM %s' % dictionary)
        ids = {str(r[0]): int(r[1]) for r in rows}
      def Encode(node):
        if isinstance(node, dict):
          if 'str' in node:
            return {'const': ids[node['str']]}
          return {k: Encode(v) for k, v in node.items()}
        if isinstance(node, list):
          return [Encode(v) for v in node]
        return node
      self.rules = Encode(self.rules)
    # Inputs: exported as headerless CSV in the column order the rules use.
    for relation, table in self.inputs.items():
      columns = self.Columns(sql_runner, table)
      has_value = any(a['has_value'] for r in self.rules for a in r['atoms']
                      if a['rel'] == relation)
      wanted = ['col%d' % f if isinstance(f, int) else f
                for f in self.input_fields.get(relation, [])]
      width = len(wanted)
      if has_value:
        wanted.append('logica_value')
      missing = [c for c in wanted if c not in columns]
      if missing:
        Error('Table %s of %s lacks columns %s.' % (table, relation, missing),
              relation)
      strings = set(string_columns.get(table, []))
      select = ', '.join(
          '(SELECT id FROM %s d WHERE d.s = t.%s)' % (dictionary, c)
          if c in strings else 't.%s' % c for c in wanted)
      path = os.path.join(workdir, relation + '.csv')
      sql_runner("COPY (SELECT %s FROM %s t) TO '%s' (HEADER false)" % (
          select, table, path), self.engine, is_final=False)
      relations[relation] = {'kind': 'input', 'arity': width,
                             'value': has_value, 'file': path}
    for relation, (path, width) in self.file_inputs.items():
      used = max([a['width'] for r in self.rules for a in r['atoms']
                  if a['rel'] == relation] + [0])
      if width is None:
        width = used
      if used > width or any(a['has_value'] for r in self.rules
                             for a in r['atoms'] if a['rel'] == relation):
        Error('%s reads more columns than its file has.' % relation, relation)
      relations[relation] = {'kind': 'input', 'arity': width,
                             'value': False, 'file': path}
    for member in self.members:
      relations[member.name] = {
          'kind': 'state', 'arity': member.arity, 'value': member.has_value,
          'aggs': [member.agg] if member.has_value else [],
          'stop': member.stop, 'internal': member.internal,
          'out': os.path.join(workdir, member.name + '.out')}
    timings['export'] = time.monotonic() - t
    t = time.monotonic()
    threads = self.program.annotations.annotations.get('@Engine', {}).get(
        self.engine, {}).get('threads') or os.cpu_count()
    # The SQL path evaluates a finite recursion N times and then once
    # more (the final pass): N + 1 passes over the component.
    max_rounds = self.repetitions
    if max_rounds < 1000000000:
      max_rounds += 1
    spec = {'threads': int(threads), 'max_rounds': max_rounds,
            'epsilon': self.epsilon, 'order': [m.name for m in self.members],
            'relations': relations, 'rules': self.rules}
    if os.environ.get('SOCRATES_SPEC_DUMP'):
      with open(os.environ['SOCRATES_SPEC_DUMP'], 'w') as f:
        json.dump(spec, f, indent=1)
    if progress:
      progress('native')
    spec_path = os.path.join(workdir, 'spec.json')
    with open(spec_path, 'w') as f:
      json.dump(spec, f)
    engine = subprocess.Popen([lib, spec_path], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
    # The engine reports every pass on a line of its own; the stats come
    # last. The display is throttled upstream.
    stats = None
    for line in engine.stdout:
      if line.startswith('pass '):
        if progress:
          progress(int(line.split()[1]))
      elif line.startswith('{'):
        stats = json.loads(line)
    errors = engine.stderr.read()
    if engine.wait() != 0 or stats is None:
      sys.stderr.write(errors)
      message = [l for l in errors.strip().split('\n') if l.strip()]
      Error('Socrates engine failed on %s: %s' % (
          self.name, message[-1] if message else 'no message'), self.name)
    timings['engine'] = time.monotonic() - t
    t = time.monotonic()
    for member in self.members:
      if member.internal:
        continue
      columns = ['col%d' % f if isinstance(f, int) else f for f in member.fields]
      # Whole numbers come back as integers, like the SQL path's.
      numeric = not stats.get(member.name + '_integral', False)
      types = ['DOUBLE' if numeric else 'BIGINT'] * len(columns)
      if member.has_value:
        columns.append('logica_value')
        types.append('DOUBLE' if numeric else 'BIGINT')
      fields = list(member.fields) + (['logica_value'] if member.has_value else [])
      decoded = []
      for c, f in zip(columns, fields):
        if dictionary and self.IsStringColumn(member.diamond_name, f):
          decoded.append('(SELECT s FROM %s d WHERE d.id = r.%s) AS %s' % (dictionary, c, c))
        else:
          decoded.append('r.%s' % c)
      sql_runner(
          "CREATE OR REPLACE TABLE %s AS SELECT %s FROM read_csv('%s', "
          "header=false, columns={%s}) r" % (
              member.table, ', '.join(decoded), relations[member.name]['out'],
              ', '.join("'%s': '%s'" % (c, t) for c, t in zip(columns, types))),
          self.engine, is_final=False)
      self.written_tables[member.name] = member.table
    if os.environ.get('SOCRATES_KEEP'):
      sys.stderr.write('socrates: files kept in %s\n' % workdir)
    else:
      for f in os.listdir(workdir):
        os.remove(os.path.join(workdir, f))
      os.rmdir(workdir)
    timings['import'] = time.monotonic() - t
    if verbose:
      sys.stderr.write('socrates %s: %s stages %s\n' % (
          self.name, json.dumps(stats),
          json.dumps({k: round(v, 3) for k, v in timings.items()})))
    return stats

  def __repr__(self):
    return 'SocraticPlan(%s: %s)' % (self.name, [m.name for m in self.members])
