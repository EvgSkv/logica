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

import copy
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
  from type_inference.research import reference_algebra
else:
  from ..compiler import neural_logica
  from ..compiler import rule_translate
  from ..common import color
  from ..type_inference.research import reference_algebra


ParsePhase = neural_logica.ParsePhase
AUX_MARKER = neural_logica.AUX_MARKER
DIAMOND_SUFFIX = neural_logica.DIAMOND_SUFFIX

AGGREGATIONS = {'Min': 'min', 'Max': 'max', 'Agg+': 'sum', 'Sum': 'sum',
                'List': 'list', 'Set': 'set', 'Count': 'count'}


def TypeDescriptor(concrete):
  """Engine type of a (very concrete) inferred type: 'num', 'str',
  'any', {'array': t} or {'record': {field: t}}."""
  if isinstance(concrete, str):
    return {'Num': 'num', 'Str': 'str'}.get(concrete, 'any')
  if isinstance(concrete, list) and len(concrete) == 1:
    return {'array': TypeDescriptor(concrete[0])}
  if isinstance(concrete, dict):
    return {'record': {f: TypeDescriptor(t) for f, t in concrete.items()}}
  return 'any'


def IsComposite(descriptor):
  return isinstance(descriptor, dict)


def DuckType(descriptor, integral=False):
  """DuckDB type to read a column of this engine type from CSV; whole
  numbers come back as integers, like the SQL path's."""
  if descriptor == 'str':
    return 'VARCHAR'
  if isinstance(descriptor, dict) and 'array' in descriptor:
    return DuckType(descriptor['array'], integral) + '[]'
  if isinstance(descriptor, dict) and 'record' in descriptor:
    return 'STRUCT(%s)' % ', '.join(
        '"%s" %s' % (f, DuckType(t, integral))
        for f, t in descriptor['record'].items())
  return 'BIGINT' if integral else 'DOUBLE'


def AggregationOf(value):
  """(engine aggregates, argument nodes) of an aggregating head value,
  or None. ArgMin/ArgMax and Array= arrive as SqlExpr calls."""
  if not (isinstance(value, dict) and 'call' in value):
    return None
  name = value['call']['predicate_name']
  args = neural_logica.FieldValues(value['call'])
  if name in AGGREGATIONS:
    return [AGGREGATIONS[name]], [args[0]]
  if name == 'SqlExpr' and len(args) == 2 and 'literal' in args[0]:
    sql = args[0]['literal'].get('the_string', {}).get('the_string', '')
    record = args[1]
    if sql.startswith('ARRAY_AGG('):
      return ['arrayagg'], [record]
    if sql.startswith('argmin(') or sql.startswith('argmax('):
      fields = {fv['field']: fv['value']['expression']
                for fv in record['record']['field_value']}
      # The argument first (the value read by others), its Min/Max
      # hidden behind it.
      return ([('argmin' if sql.startswith('argmin(') else 'argmax'),
               ('min' if sql.startswith('argmin(') else 'max')],
              [fields['a'], fields['v']])
  return None


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
    self.aggs = []           # engine aggregates of the value columns
    self.hidden = []         # value columns not read back (ArgMin's Min)
    # Aggregated fields (`length? Min= ...`) and the aggregated value:
    # field -> its engine aggregates; laid out as value columns, the
    # first of a field visible, the rest hidden.
    self.field_aggs = {}
    self.value_columns = []  # (field, index into its aggregates)
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
    # Compile stop predicates as members and evaluate them last in each
    # pass. The engine stops when one becomes non-empty, or when its own
    # fixpoint check (with epsilon for sums) detects no further changes.
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
      member.value_columns = []
      for f in sorted(member.field_aggs, key=lambda f: (f == 'logica_value', f)):
        for i in range(len(member.field_aggs[f])):
          member.value_columns.append((f, i))
      member.aggs = [member.field_aggs[f][i] for f, i in member.value_columns]
      member.hidden = [c for c, (f, i) in enumerate(member.value_columns) if i > 0]
      member.has_value = bool(member.value_columns)
      member.agg = member.aggs[0] if member.aggs else 'or'
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

  def FieldType(self, predicate_name, field):
    """Engine type descriptor of a predicate's field ('any' if unknown)."""
    signature = self.program.predicate_signatures.get(predicate_name, {})
    if field not in signature:
      return 'any'
    return TypeDescriptor(
        reference_algebra.VeryConcreteType(signature[field]))

  def IsStringColumn(self, predicate_name, field):
    """Whether the inferred type of a predicate's field is a string."""
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
      # Aggregated fields and the aggregated value are value columns;
      # the other fields are keys.
      keys = []
      for k, v in rs.select.items():
        if k == '*':
          Error('Socratic recursion does not support record spreading '
                '(..r) in heads.', rs.full_rule_text or member.name)
        aggregation = AggregationOf(v)
        if aggregation:
          member.field_aggs[k] = aggregation[0]
        elif k != 'logica_value':
          keys.append(k)
      member.arity = max(member.arity, len(keys))
      for k in keys:
        if k not in member.fields:
          member.fields.append(k)
      value = rs.select.get('logica_value')
      if value is not None:
        if 'logica_value' not in member.field_aggs:
          # A functional (=) definition is a set of rows in the SQL path
          # (several rules may give several values; aggregation, if any,
          # happens in the readers): the value is one more key column.
          if member.field_aggs:
            Error('Socratic recursion does not support a functional '
                  'predicate with aggregated fields.',
                  rs.full_rule_text or member.name)
          member.functional = True
      aux = [p for p in rs.tables.values() if AUX_MARKER in p]
      if aux and len(rs.tables) == 1:
        [aux_name] = set(aux)
        for aux_rule in self.Rules(aux_name):
          inner = self.Structure(aux_rule)
          # The auxiliary supplies raw contributions, not necessarily the
          # aggregate's arguments. Preserve the outer expression: e.g.
          # Shortest(p) = ArgMin(p -> Size(p)) transforms each raw path
          # into both an argument and its score before aggregation.
          outer = copy.deepcopy({
              'select': rs.select, 'constraints': rs.constraints,
              'vars_unification': rs.vars_unification,
              'unnestings': rs.unnestings})
          for (_, field), var in rs.vars_map.items():
            rule_translate.ReplaceVariable(var, inner.select[field], outer)
          inner.select = outer['select']
          inner.constraints.extend(outer['constraints'])
          inner.vars_unification.extend(outer['vars_unification'])
          inner.unnestings.extend(outer['unnestings'])
          inner.ElliminateInternalVariables(assert_full_ellimination=False)
          self.rules.append(self.CompileRule(member, inner))
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
    aggregation = AggregationOf(value)
    if not aggregation:
      Error('Socratic recursion does not support aggregating expression '
            '%s.' % color.Warn(neural_logica.ExpressionText(value)),
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
    aux.field_aggs = {'logica_value': aggregation[0]}
    rule = self.CompileRule(aux, crs, aggregated=value, head_keys=keys)
    # Keys the expression's own atoms do not bind are asked for: a demand
    # member lists them (the key domain is then the rule's, not the
    # expression's).
    bound = set(v['var'] for a in rule['atoms']
                for v in a.get('fields', {}).values())
    bound |= set(a['args'][1]['var'] for a in rule['atoms'] if a.get('unnest'))
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
    outer_vars |= rule_translate.AllMentionedVariables(rs.unnestings)
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
        if 'the_null' in literal:
          return {'null': True}
        if 'the_list' in literal:
          return {'op': 'MakeArray',
                  'args': [Expr(e) for e in literal['the_list']['element']]}
        if 'the_bool' in literal:
          return {'const': 1 if literal['the_bool']['value'] else 0}
        if 'the_string' in literal:
          # Encoded through the string dictionary at run time.
          value = literal['the_string']['the_string']
          self.strings.add(value)
          return {'str': value}
        Error('Socratic recursion supports only number and string literals.',
              context)
      if isinstance(node, dict) and 'record' in node:
        args = []
        for fv in node['record']['field_value']:
          self.strings.add(str(fv['field']))
          args += [{'str': str(fv['field'])}, Expr(fv['value']['expression'])]
        return {'op': 'MakeRecord', 'args': args}
      if isinstance(node, dict) and 'subscript' in node:
        field = str(node['subscript']['subscript']['literal']['the_symbol']['symbol'])
        self.strings.add(field)
        return {'op': 'Field', 'args': [Expr(node['subscript']['record']),
                                        {'str': field}]}
      if isinstance(node, dict) and 'call' in node:
        call = node['call']
        op = call['predicate_name']
        args = [fv['value']['expression']
                for fv in call['record']['field_value']]
        if op == 'ValueOfUnnested' and len(args) == 1:
          return Expr(args[0])
        # Extracting calls into table reads can replace typed operands
        # with untyped variables. The concatenation itself keeps its
        # inferred result type, so consult it before the operand types.
        if op == '++' and len(args) == 2 and any(
            a.get('type', {}).get('rendered_type') == 'Str'
            for a in [node] + args):
          op = 'StrConcat'  # strings and arrays share the operator
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
    # `x in list`: an atom walking the elements of the list.
    for element, source in [(u[0], u[1]) for u in rs.unnestings]:
      if not IsVariable(element):
        Error('Socratic recursion supports `in` only with a variable on '
              'the left.', context)
      atoms.append({'rel': '__unnest', 'unnest': True,
                    'args': [Expr(source),
                             {'var': canonical(VariableName(element))}]})
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
      keys = {k: Expr(v) for k, v in rs.select.items()
              if k != 'logica_value' and k not in member.field_aggs}
    value = None
    if member.functional:
      keys['logica_value'] = Expr(rs.select['logica_value'])
    # Value columns by field: the aggregated fields of the head and
    # the aggregated value (`aggregated` for a hoisted expression).
    value_fields = {}
    for f, v in rs.select.items():
      if f == 'logica_value' and aggregated is not None:
        v = aggregated
      aggregation = AggregationOf(v)
      if aggregation and not (f == 'logica_value' and member.functional):
        value_fields[f] = [Expr(a) for a in aggregation[1]]
      elif f in member.field_aggs:
        # A rule of the multi-body auxiliary gives the raw value: for
        # ArgMin/ArgMax the {arg, value} record of `->`.
        if len(member.field_aggs[f]) == 2:
          self.strings.update(['arg', 'value'])
          value_fields[f] = [
              {'op': 'Field', 'args': [Expr(v), {'str': 'arg'}]},
              {'op': 'Field', 'args': [Expr(v), {'str': 'value'}]}]
        else:
          value_fields[f] = [Expr(v)]
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
            'value_fields': value_fields,
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
    value_fields = rule.pop('value_fields')
    rule['values'] = []
    for f, i in member.value_columns:
      if f not in value_fields or i >= len(value_fields[f]):
        Error('A rule of %s does not aggregate %s.' % (
            color.Warn(member.name), f), member.name)
      rule['values'].append(value_fields[f][i])
    for atom in rule['atoms']:
      if atom.get('unnest'):
        atom['width'] = 2
        atom['has_value'] = False
        continue
      fields = atom.pop('fields')
      rel = atom['rel']
      if rel in [m.name for m in self.members]:
        m = next(mm for mm in self.members if mm.name == rel)
        columns = self.ColumnsOf(rel)
        # Value columns follow the keys; a field's visible column first.
        value_at = {}
        for c, (f, i) in enumerate(m.value_columns):
          value_at.setdefault(f, m.arity + c)
        args = [None] * (m.arity + len(m.value_columns))
        has_value = False
        for f, expr in fields.items():
          if f in value_at:
            args[value_at[f]] = expr
            has_value = True
          elif f in columns:
            args[columns[f]] = expr
          else:
            Error('%s has no field %s.' % (color.Warn(rel), f), rel)
        atom['args'] = args
        atom['has_value'] = has_value
        atom['width'] = m.arity
        continue
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
        if f == 'logica_value':
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
    dictionary = 'socrates_dict_' + self.name
    if True:
      parts = ['SELECT %s AS s FROM %s' % (c, t)
               for t, cs in string_columns.items() for c in cs]
      parts += ["SELECT '%s' AS s" % v.replace("'", "''") for v in sorted(self.strings)]
      parts = parts or ["SELECT NULL::VARCHAR AS s"]
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
    # Strings inside composite values are interned by the engine: it
    # receives the dictionary and reports the strings it added.
    dictionary_spec = None
    if dictionary:
      dictionary_spec = {'file': os.path.join(workdir, 'dict.csv'),
                         'out': os.path.join(workdir, 'dict_out.csv')}
      sql_runner("COPY (SELECT id, s FROM %s) TO '%s' (HEADER false)" % (
          dictionary, dictionary_spec['file']), self.engine, is_final=False)
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
      fields = list(self.input_fields.get(relation, []))
      if has_value:
        fields.append('logica_value')
      types = [self.FieldType(relation, f) for f in fields]
      select = ', '.join(
          '(SELECT id FROM %s d WHERE d.s = t.%s)' % (dictionary, c)
          if c in strings else
          'to_json(t.%s)' % c if IsComposite(t) else 't.%s' % c
          for c, t in zip(wanted, types))
      path = os.path.join(workdir, relation + '.csv')
      sql_runner("COPY (SELECT %s FROM %s t) TO '%s' (HEADER false)" % (
          select, table, path), self.engine, is_final=False)
      relations[relation] = {'kind': 'input', 'arity': width,
                             'value': has_value, 'file': path,
                             'types': types}
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
      types = [self.FieldType(member.diamond_name, f) for f in member.fields]
      types += [self.FieldType(member.diamond_name, f) if i == 0 else 'any'
                for f, i in member.value_columns]
      relations[member.name] = {
          'kind': 'state', 'arity': member.arity, 'value': member.has_value,
          'aggs': member.aggs if member.has_value else [],
          'hidden': member.hidden, 'types': types,
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
            'dictionary': dictionary_spec,
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
    # The engine's trace streams through; otherwise its complaints are
    # collected for the error message.
    tracing = bool(os.environ.get('SOCRATES_TRACE') or os.environ.get('SOCRATES_EXPLAIN'))
    engine = subprocess.Popen([lib, spec_path], stdout=subprocess.PIPE,
                              stderr=None if tracing else subprocess.PIPE,
                              text=True)
    # The engine reports every pass on a line of its own; the stats come
    # last. The display is throttled upstream.
    stats = None
    try:
      for line in engine.stdout:
        if line.startswith('pass '):
          if progress:
            progress(int(line.split()[1]))
        elif line.startswith('{'):
          stats = json.loads(line)
      errors = '' if tracing else engine.stderr.read()
    finally:
      if engine.poll() is None:  # interrupted: the engine goes too
        engine.kill()
        engine.wait()
    if engine.wait() != 0 or stats is None:
      sys.stderr.write(errors)
      message = [l for l in errors.strip().split('\n') if l.strip()]
      Error('Socrates engine failed on %s: %s' % (
          self.name, message[-1] if message else 'no message'), self.name)
    timings['engine'] = time.monotonic() - t
    t = time.monotonic()
    if dictionary_spec and os.path.getsize(dictionary_spec['out']) > 0:
      sql_runner("INSERT INTO %s SELECT id, s FROM read_csv('%s', header=false, "
                 "columns={'id': 'BIGINT', 's': 'VARCHAR'})" % (
                     dictionary, dictionary_spec['out']),
                 self.engine, is_final=False)
    for member in self.members:
      if member.internal:
        continue
      fields = list(member.fields) + [f for f, i in member.value_columns if i == 0]
      columns = ['col%d' % f if isinstance(f, int) else f for f in fields]
      # Whole numbers come back as integers, like the SQL path's;
      # composite values as their DuckDB types.
      integral = stats.get(member.name + '_integral') or [False] * len(fields)
      types = [DuckType(self.FieldType(member.diamond_name, f), whole)
               if IsComposite(self.FieldType(member.diamond_name, f))
               else ('BIGINT' if whole else 'DOUBLE')
               for f, whole in zip(fields, integral)]
      decoded = []
      for c, f in zip(columns, fields):
        if dictionary and self.IsStringColumn(member.diamond_name, f):
          decoded.append('(SELECT s FROM %s d WHERE d.id = r.%s) AS %s' % (dictionary, c, c))
        else:
          decoded.append('r.%s' % c)
      if os.path.getsize(relations[member.name]['out']) == 0:
        # An empty predicate: DuckDB cannot sniff an empty file.
        sql_runner(
            "CREATE OR REPLACE TABLE %s AS SELECT %s FROM (SELECT %s WHERE false) r" % (
                member.table, ', '.join(decoded),
                ', '.join("CAST(NULL AS %s) AS %s" % (t, c) for c, t in zip(columns, types))),
            self.engine, is_final=False)
      else:
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
