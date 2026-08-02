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

"""Neural execution of Logica recursive covers.

@Recursive(P, mode: "neural") makes the recursive cover of P iterate as a
dense tensor computation in JAX instead of a SQL loop.

The diamond recursion functor produces for every cover member p a predicate
p_diamond whose single aggregated rule is exactly the rewrite w_p of the
stabilization semantics: it reads portal predicates (the previous state)
and extensional relations, and combines candidate values with its
aggregation (+= / Min= / Max=). NeuralPlan translates these rules into a
tensor program:

  * string and numeric keys are indexed into dense axes (one shared domain
    per key type);
  * every relation becomes a pair of dense arrays (support mask, values),
    so that "row is absent" is distinguished from "value is 0";
  * every rule contribution becomes broadcast + elementwise ops + a
    reduction in the semiring of the head aggregation;
  * inner aggregating expressions (Sum{...}) reduce local axes; an empty
    inner aggregation makes the contribution invalid for that row, exactly
    like the NULL it produces in SQL.

At run time the plan reads its input tables through the SQL runner,
iterates the jitted sweep in DiamondOrder until stabilization (or the
repetition cap), and writes the stabilized relations of all cover members
back into their portal tables. The final Gauss-Seidel SQL pass computing p
from p_diamond is unchanged and runs on top of the written tables.
"""

import collections

if '.' not in __package__:
  from common import color
  from compiler import functors
  from compiler import rule_translate
  from parser_py import parse
  from type_inference.research import reference_algebra
else:
  from ..common import color
  from ..compiler import functors
  from ..compiler import rule_translate
  from ..parser_py import parse
  from ..type_inference.research import reference_algebra


class NeuralCompileException(rule_translate.RuleCompileException):
  """Neural fragment violation with a nice message."""


def Error(message, context):
  raise NeuralCompileException(message, context)


# Aggregation of the member head: reduction kind and neutral element.
AGGREGATIONS = {
    'Agg+': ('sum', 0.0),
    'Min': ('min', float('inf')),
    'Max': ('max', float('-inf')),
}

# Inner aggregating expressions Sum{...}, Min{...}, Max{...}. AnyValue
# picks a deterministic representative. User-defined aggregations resolve
# to expressions over these primitives via their defining rule.
INNER_AGGREGATIONS = {
    'Sum': 'sum',
    'Min': 'min',
    'Max': 'max',
    'AnyValue': 'any',
}

NEUTRAL = {'sum': 0.0, 'min': float('inf'), 'max': float('-inf'),
           'any': float('-inf')}

ELEMENTWISE_OPS = {'+', '-', '*', '/', '^', 'Least', 'Greatest',
                   'Abs', 'Exp', 'Log', 'Sqrt', 'Sin', 'Cos', 'Floor'}

COMPARISON_OPS = {'==', '!=', '<', '<=', '>', '>='}

LOGICAL_OPS = {'&&', '||', '!'}


def ExpressionText(node):
  """Source text of an expression, if the parser recorded it."""
  heritage = node.get('expression_heritage') if isinstance(node, dict) else None
  return str(heritage) if heritage is not None else None

DIAMOND_SUFFIX = '_diamond'
PORTAL_SUFFIX = '_portal'
AUX_MARKER = '_MultBodyAggAux'


def FieldValues(call_node):
  """Argument expressions of a call, in syntactic order."""
  return [fv['value']['expression']
          for fv in call_node['record']['field_value']]


def IsVariable(node):
  return isinstance(node, dict) and 'variable' in node


def VariableName(node):
  return node['variable']['var_name']


def LiteralListValues(node):
  """Values of a literal list AST node, or None if not a literal list."""
  literal = node.get('literal') if isinstance(node, dict) else None
  if not literal or 'the_list' not in literal:
    return None
  values = []
  for element in literal['the_list']['element']:
    value = LiteralValue(element)
    if value is None:
      # Constant-fold unary minus: [-1, 0, 1] may parse as calls.
      if (isinstance(element, dict) and 'call' in element and
          element['call']['predicate_name'] == '-'):
        arguments = FieldValues(element['call'])
        inner = LiteralValue(arguments[0]) if len(arguments) == 1 else None
        if inner is not None:
          value = -inner
    if value is None:
      return None
    values.append(value)
  return values


def LiteralValue(node):
  """Python value of a literal AST node, or None if not a literal."""
  literal = node.get('literal') if isinstance(node, dict) else None
  if not literal:
    return None
  if 'the_number' in literal:
    text = literal['the_number']['number']
    return float(text) if ('.' in text or 'e' in text or 'E' in text) else int(
        text)
  if 'the_string' in literal:
    return literal['the_string']['the_string']
  if 'the_bool' in literal:
    return literal['the_bool']['the_bool'] in (True, 'true')
  return None


class UnionFind(object):
  def __init__(self):
    self.parent = {}

  def Find(self, x):
    self.parent.setdefault(x, x)
    while self.parent[x] != x:
      self.parent[x] = self.parent[self.parent[x]]
      x = self.parent[x]
    return x

  def Union(self, a, b):
    self.parent[self.Find(a)] = self.Find(b)


class Relation(object):
  """A relation participating in the tensor program."""

  def __init__(self, name, key_fields, key_types, has_value):
    self.name = name
    self.key_fields = key_fields  # Field names in table column order.
    self.key_types = key_types    # 'Str' | 'Num' per key field.
    self.has_value = has_value

  def __repr__(self):
    return 'Relation(%s, %s, value: %s)' % (
        self.name, list(zip(self.key_fields, self.key_types)), self.has_value)


class Contribution(object):
  """One rule contribution to a member: a masked expression over axes."""

  def __init__(self):
    self.axes = []              # Canonical variables, ordered.
    self.axis_type = {}         # var -> 'Str' | 'Num'.
    self.reads = []             # (relation name, {field -> var}, value var).
    self.head = []              # Per member key: ('var', v) or ('const', c).
    self.value_expr = None      # Expression AST or None.
    self.constraints = []       # Comparison expression ASTs.
    self.memberships = []       # (var, values): axes over literal lists.
    self.definitions = {}       # var -> expression AST.
    self.canonical = {}         # var -> canonical var.
    self.rule_text = ''

  def __repr__(self):
    return 'Contribution(axes: %s, reads: %s)' % (self.axes, self.reads)


class Member(object):
  """A cover member: its key signature and rule contributions."""

  def __init__(self, name, diamond_name):
    self.name = name
    self.diamond_name = diamond_name
    self.table = None           # Portal table to write back.
    self.key_fields = []
    self.key_types = []
    self.has_value = True
    self.aggregation = None     # 'sum' | 'min' | 'max' | 'or'.
    self.neutral = None
    self.contributions = []


def ExtractStructure(program, rule, allocator):
  """Rule -> normalized RuleStructure with injections applied."""
  rs = rule_translate.ExtractRuleStructure(rule, allocator, None)
  rs.ElliminateInternalVariables(assert_full_ellimination=False)
  program.RunInjections(rs, allocator)
  rs.ElliminateInternalVariables(assert_full_ellimination=False)
  return rs


def BoundVariables(rs):
  """Variables of the structure bound by tables or unnestings."""
  bound = set(rs.vars_map.values())
  changed = True
  while changed:
    changed = False
    for unnesting in rs.unnestings:
      element, source = unnesting[0], unnesting[1]
      element_vars = set(rule_translate.AllMentionedVariables(element))
      source_vars = set(rule_translate.AllMentionedVariables(
          source, dive_in_combines=True))
      if source_vars <= bound and not element_vars <= bound:
        bound |= element_vars
        changed = True
    for u in rs.vars_unification:
      for a, b in [(u['left'], u['right']), (u['right'], u['left'])]:
        a_vars = set(rule_translate.AllMentionedVariables(a))
        b_vars = set(rule_translate.AllMentionedVariables(b))
        if b_vars <= bound and not a_vars <= bound and IsVariable(a):
          bound |= a_vars
          changed = True
  return bound


def IsFunctional(predicate_name, rules_of):
  """A predicate is functional if its head needs externally bound variables.

  Such predicates (e.g. Clip(a, b, c) = ..., or s(x) = ToString(x)) have no
  finite table and are always injected into their callers.
  """
  for rule in rules_of[predicate_name]:
    allocator = rule_translate.NamesAllocator()
    try:
      rs = rule_translate.ExtractRuleStructure(rule, allocator, None)
      rs.ElliminateInternalVariables(assert_full_ellimination=False)
    except rule_translate.RuleCompileException:
      return False
    select_vars = set(rule_translate.AllMentionedVariables(
        rs.select, dive_in_combines=True))
    if select_vars - BoundVariables(rs):
      return True
  return False


def AppendAutoGrounds(rules):
  """Grounds input relations of neural iterations, so that the neural
  runtime can read them from tables."""
  neural_iterations = []
  for rule in rules:
    if rule['head']['predicate_name'] != '@Iteration':
      continue
    fields = {fv['field']: fv['value']['expression']
              for fv in rule['head']['record']['field_value']}
    if 'neural' not in fields or LiteralValue(fields['neural']) is not True:
      continue
    neural_iterations.append(fields)
  if not neural_iterations:
    return

  rules_of = collections.defaultdict(list)
  grounded = set()
  for rule in rules:
    head = rule['head']['predicate_name']
    if head == '@Ground':
      subject = rule['head']['record']['field_value'][0]['value'][
          'expression'].get('literal', {}).get('the_predicate', {}).get(
          'predicate_name')
      if subject:
        grounded.add(subject)
    elif head[0] != '@':
      rules_of[head].append(rule)

  candidates = set()
  for fields in neural_iterations:
    diamond_predicates = [
        e['literal']['the_predicate']['predicate_name']
        for e in fields['predicates']['literal']['the_list']['element']]
    members = {p[:-len(DIAMOND_SUFFIX)] for p in diamond_predicates
               if p.endswith(DIAMOND_SUFFIX)}
    frontier = list(diamond_predicates)
    seen = set(frontier)
    while frontier:
      p = frontier.pop()
      referenced = set()
      def Collect(x):
        if isinstance(x, dict) and 'predicate_name' in x:
          referenced.add(x['predicate_name'])
        return []
      for rule in rules_of.get(p, []):
        functors.Walk(rule['head']['record'], Collect)
        if 'body' in rule:
          functors.Walk(rule['body'], Collect)
      for name in referenced:
        if name in seen:
          continue
        seen.add(name)
        if AUX_MARKER in name:
          frontier.append(name)
          continue
        if (name in members or name[0] == '@' or
            name.endswith(PORTAL_SUFFIX) or name.endswith('_RZero') or
            name.endswith(DIAMOND_SUFFIX) or '_ROne' in name):
          continue
        if name not in rules_of:
          continue  # Built-in or external table.
        candidates.add(name)

  for name in sorted(candidates):
    if name in grounded or IsFunctional(name, rules_of):
      continue
    rules.extend(parse.ParseFile('@Ground(%s);' % name)['rule'])


def CheckNeuralPredicatesIterate(annotations):
  """Neural mode of a non-recursive predicate would be silently ignored;
  telling the user instead."""
  requested = {
      p for p, entry in annotations.annotations.get('@Recursive', {}).items()
      if entry.get('mode') == 'neural'}
  if not requested:
    return
  covered = set()
  for iteration in annotations.Iterations().values():
    if iteration.get('neural'):
      covered |= {p[:-len(DIAMOND_SUFFIX)]
                  for p in iteration['predicates']
                  if p.endswith(DIAMOND_SUFFIX)}
  for p in sorted(requested - covered):
    Error('Predicate %s requests neural recursion, but it is not '
          'recursive. Neural execution iterates a recursive predicate to '
          'stabilization, so %s must depend on itself (directly or '
          'through other predicates).' % (color.Warn(p), color.Warn(p)), p)


class NeuralPlan(object):
  """Tensor program of one neural iteration.

  Built at compile time from the diamond rules; executed by Run() through
  the SQL runner.
  """

  def __init__(self, program, iteration_name, iteration):
    self.program = program
    self.name = iteration_name
    self.engine = program.annotations.Engine()
    self.repetitions = int(iteration['repetitions'])
    self.epsilon = 1e-10
    for member_args in program.annotations.annotations.get(
        '@Recursive', {}).values():
      if member_args.get('mode') == 'neural' and 'epsilon' in member_args:
        self.epsilon = float(member_args['epsilon'])
    self.members = []           # In DiamondOrder.
    self.relations = {}         # name -> Relation, inputs and state.
    self.input_tables = {}      # relation name -> physical table.
    self.constant_keys = {'Str': set(), 'Num': set()}  # Keys from rules.
    self.synthetic_count = 0    # For axes of computed head keys.
    self.allocator = rule_translate.NamesAllocator()
    for diamond_name in iteration['predicates']:
      if not diamond_name.endswith(DIAMOND_SUFFIX):
        Error('Neural iteration got a non-diamond predicate %s.' %
              color.Warn(diamond_name), self.name)
      self.CompileMember(diamond_name)
    self.FinalizeTypes()

  def FinalizeTypes(self):
    """Resolves key types that SQL inference left as Any.

    Types flow through the join structure: a variable joining a typed key
    types the untyped keys it joins, member keys are typed by their head
    variables. Iterates to fixpoint.
    """
    changed = True
    while changed:
      changed = False
      for member in self.members:
        for contribution in member.contributions:
          axis_type = contribution.axis_type
          for name, key_map, _ in contribution.reads:
            relation = self.relations[name]
            for field, var in key_map.items():
              position = relation.key_fields.index(field)
              relation_type = relation.key_types[position]
              known = axis_type.get(var)
              if relation_type and not known:
                axis_type[var] = relation_type
                changed = True
              elif known and not relation_type:
                relation.key_types[position] = known
                changed = True
          for position, (kind, key) in enumerate(contribution.head):
            if kind != 'var':
              continue
            known = axis_type.get(key)
            member_type = member.key_types[position]
            if member_type and not known:
              axis_type[key] = member_type
              changed = True
            elif known and not member_type:
              member.key_types[position] = known
              changed = True
    for member in self.members:
      for position, member_type in enumerate(member.key_types):
        if member_type is None:
          Error('Could not infer whether key column %s of %s holds '
                'strings or numbers; bind it through a typed relation.' %
                (color.Warn(str(member.key_fields[position])),
                 color.Warn(member.name)), member.name)
      for contribution in member.contributions:
        for variable in contribution.axes:
          if contribution.axis_type.get(variable) is None:
            Error('Could not infer whether a join variable of %s holds '
                  'strings or numbers; bind it through a typed relation. '
                  'Rule: %s' % (color.Warn(member.name),
                                contribution.rule_text),
                  contribution.rule_text)
    for name, relation in self.relations.items():
      for position, relation_type in enumerate(relation.key_types):
        if relation_type is None and name in self.input_tables:
          Error('Could not infer whether key column %s of %s holds '
                'strings or numbers.' %
                (color.Warn(str(relation.key_fields[position])),
                 color.Warn(name)), name)

  # ----------------------------- Compilation -----------------------------

  def PredicateSignature(self, predicate_name):
    signatures = self.program.predicate_signatures
    if predicate_name not in signatures:
      Error('Neural compilation needs type inference, but predicate '
            '%s has no signature.' % color.Warn(predicate_name),
            self.name)
    return signatures[predicate_name]

  def Signature(self, predicate_name, display_name=None):
    """([key fields], [key types], has_value) of a predicate."""
    display_name = display_name or predicate_name
    signature = self.PredicateSignature(predicate_name)
    key_fields = []
    key_types = []
    has_value = False
    for field in sorted(signature,
                        key=lambda f: (isinstance(f, str), f)):
      rendered = reference_algebra.RenderType(
          reference_algebra.VeryConcreteType(signature[field]))
      if field == 'logica_value':
        has_value = True
        if rendered not in ('Num', 'Bool'):
          Error('Neural iteration computes numbers: the value of %s is '
                'of type %s. Only numeric values can live in tensors.' %
                (color.Warn(display_name), color.Warn(rendered)),
                display_name)
        continue
      if rendered == 'Any':
        # SQL inference could not pin the type (e.g. a column typed only
        # through a portal); the join structure of the plan resolves it
        # in FinalizeTypes.
        key_fields.append(field)
        key_types.append(None)
        continue
      if rendered not in ('Str', 'Num'):
        Error('Neural keys must be strings or numbers; column %s of %s '
              'is %s.' %
              (color.Warn(str(field)), color.Warn(display_name),
               color.Warn(rendered)), display_name)
      key_fields.append(field)
      key_types.append(rendered)
    return key_fields, key_types, has_value

  def RelationOf(self, predicate_name, context):
    """Relation spec of a leaf predicate: a portal or a grounded input."""
    if predicate_name in self.relations:
      return self.relations[predicate_name]
    key_fields, key_types, has_value = self.Signature(predicate_name)
    relation = Relation(predicate_name, key_fields, key_types, has_value)
    self.relations[predicate_name] = relation
    if not predicate_name.endswith(PORTAL_SUFFIX):
      ground = self.program.annotations.Ground(predicate_name)
      if ground is None:
        Error('Neural rules may only read recursive state and stored '
              'relations. Predicate %s is neither.' %
              color.Warn(predicate_name), context)
      self.input_tables[predicate_name] = ground.table_name
    return relation

  def CompileMember(self, diamond_name):
    member_name = diamond_name[:-len(DIAMOND_SUFFIX)]
    member = Member(member_name, diamond_name)
    # Checking the signature first: it produces the clearest errors
    # (e.g. string-valued predicates are outside of the fragment).
    member.key_fields, member.key_types, member.has_value = self.Signature(
        diamond_name, member_name)
    rules = [r for name, r in self.program.rules if name == diamond_name]
    assert rules, 'Diamond predicate %s has no rules.' % diamond_name
    rs = ExtractStructure(self.program, rules[0], self.allocator)

    ground = self.program.annotations.Ground(diamond_name)
    assert ground, 'Diamond predicates are always grounded.'
    member.table = ground.table_name

    # The diamond rule aggregates over either the multi-body auxiliary
    # predicate or directly over its own body.
    if member.has_value:
      value = rs.select.get('logica_value')
      if not (isinstance(value, dict) and 'call' in value and
              value['call']['predicate_name'] in AGGREGATIONS):
        Error('Neural predicate %s must aggregate with one of '
              '+=, Min= or Max=.' % color.Warn(member_name),
              rs.full_rule_text or member_name)
      member.aggregation, member.neutral = AGGREGATIONS[
          value['call']['predicate_name']]
      aggregated_expr = FieldValues(value['call'])[0]
    else:
      member.aggregation, member.neutral = 'or', False
      aggregated_expr = None
    if len(rules) != 1:
      # Multiple diamond rules survive only when bodies could not be
      # merged, which the aggregation check above should have explained.
      Error('Neural predicate %s has %d rules that could not be merged '
            'into a single rewrite; only +=, Min= and Max= rules can '
            'iterate neurally.' % (color.Warn(member_name), len(rules)),
            member_name)

    aux_predicates = [p for p in rs.tables.values() if AUX_MARKER in p]
    if aux_predicates:
      [aux_name] = set(aux_predicates)
      for _, aux_rule in [(n, r) for n, r in self.program.rules
                          if n == aux_name]:
        aux_rs = ExtractStructure(self.program, aux_rule, self.allocator)
        member.contributions.append(
            self.ExtractContribution(member, aux_rs, aux=True))
    else:
      member.contributions.append(
          self.ExtractContribution(member, rs, aux=False,
                                   aggregated_expr=aggregated_expr))
    self.members.append(member)

  def ExtractContribution(self, member, rs, aux, aggregated_expr=None):
    """Turns a rule structure into a Contribution of the member."""
    contribution = Contribution()
    contribution.rule_text = rs.full_rule_text or member.name

    # Canonicalize variables: identify variables unified with each other,
    # including the two sides of the `=` pseudo-relation.
    union_find = UnionFind()
    for u in rs.vars_unification:
      if IsVariable(u['left']) and IsVariable(u['right']):
        union_find.Union(VariableName(u['left']), VariableName(u['right']))
    equality_aliases = collections.defaultdict(dict)
    for (alias, field), var in rs.vars_map.items():
      if alias is not None and rs.tables[alias] == '=':
        equality_aliases[alias][field] = var
    for alias, sides in equality_aliases.items():
      union_find.Union(sides['left'], sides['right'])
    canonical = union_find.Find
    contribution.canonical = union_find

    # Bind table columns.
    axis_of = {}       # canonical var -> 'Str' | 'Num'.
    value_vars = {}    # canonical var -> alias.
    reads = collections.OrderedDict()  # alias -> [relation, {field: var}, v]
    for (alias, field), var in rs.vars_map.items():
      if alias is None or rs.tables[alias] == '=':
        continue  # Unnested variables are handled below.
      relation = self.RelationOf(rs.tables[alias], contribution.rule_text)
      var = canonical(var)
      reads.setdefault(alias, [relation, {}, None])
      if field == 'logica_value':
        reads[alias][2] = var
        value_vars[var] = alias
      else:
        reads[alias][1][field] = var

    for alias, (relation, key_map, value_var) in reads.items():
      if set(key_map) != set(relation.key_fields):
        Error('Neural read of %s must bind all its keys; rule of %s binds '
              '%s out of %s.' %
              (color.Warn(relation.name), color.Warn(member.name),
               sorted(map(str, key_map)),
               sorted(map(str, relation.key_fields))),
              contribution.rule_text)
      for field, var in key_map.items():
        field_type = relation.key_types[relation.key_fields.index(field)]
        if var in value_vars:
          Error('Neural fragment does not allow joining a key with a '
                'value; variable in rule of %s.' % color.Warn(member.name),
                contribution.rule_text)
        known = axis_of.get(var)
        if known and field_type and known != field_type:
          Error('Variable joins keys of different types (Str vs Num) in '
                'rule of %s.' % color.Warn(member.name),
                contribution.rule_text)
        axis_of[var] = known or field_type
      contribution.reads.append(
          (relation.name, dict(key_map), value_var))

    # Unnestings over literal lists (dx in [-1, 0, 1]) are bounded domains:
    # the variable becomes an axis restricted by a membership mask.
    for unnesting in rs.unnestings:
      element, source = unnesting[0], unnesting[1]
      values = LiteralListValues(source)
      if not IsVariable(element) or values is None or not values:
        Error('Neural rules may unnest (with the in-operator) only literal '
              'lists in rules of %s.' % color.Warn(member.name),
              contribution.rule_text)
      var = canonical(VariableName(element))
      if all(isinstance(v, (int, float)) for v in values):
        element_type = 'Num'
      elif all(isinstance(v, str) for v in values):
        element_type = 'Str'
      else:
        Error('Neural unnested lists must hold numbers or strings: %s' %
              contribution.rule_text, contribution.rule_text)
      if axis_of.get(var) not in (None, element_type):
        Error('Variable joins keys of different types (Str vs Num) in '
              'rule of %s.' % color.Warn(member.name),
              contribution.rule_text)
      axis_of[var] = element_type
      self.constant_keys[element_type] |= set(values)
      contribution.memberships.append((var, tuple(values)))

    # Remaining unifications: a variable bound by tables gets an equality
    # constraint; an unbound variable gets a definition.
    bound = set(axis_of) | set(value_vars)
    for u in rs.vars_unification:
      left, right = u['left'], u['right']
      if IsVariable(left) and IsVariable(right):
        continue  # Handled by canonicalization.
      if IsVariable(left) or IsVariable(right):
        variable_node, expression = (
            (left, right) if IsVariable(left) else (right, left))
        variable = canonical(VariableName(variable_node))
        if variable not in bound:
          contribution.definitions[variable] = expression
          continue
      contribution.constraints.append(
          {'call': {'predicate_name': '==', 'record': {'field_value': [
              {'field': 'left', 'value': {'expression': left}},
              {'field': 'right', 'value': {'expression': right}}]}}})
    contribution.constraints.extend(rs.constraints)

    # Head keys.
    key_selects = [(k, v) for k, v in rs.select.items()
                   if k != 'logica_value']
    if len(key_selects) != len(member.key_fields):
      Error('Rule of %s selects %d keys, member has %d.' %
            (color.Warn(member.name), len(key_selects),
             len(member.key_fields)), contribution.rule_text)
    for position, (k, expr) in enumerate(key_selects):
      if IsVariable(expr):
        contribution.head.append(('var', canonical(VariableName(expr))))
      elif LiteralValue(expr) is not None:
        contribution.head.append(('const', LiteralValue(expr)))
        # Constant keys must exist in the domain even if no input relation
        # mentions them.
        self.constant_keys[member.key_types[position]].add(
            LiteralValue(expr))
      else:
        # A computed key, e.g. Life(x, y, n + 1): the head position
        # becomes a fresh synthetic axis m constrained by m == n + 1.
        self.synthetic_count += 1
        variable = 'neural_head_%d' % self.synthetic_count
        axis_of[variable] = member.key_types[position]
        contribution.head.append(('var', variable))
        contribution.constraints.append(
            {'call': {'predicate_name': '==', 'record': {'field_value': [
                {'field': 'left', 'value': {'expression':
                    {'variable': {'var_name': variable}}}},
                {'field': 'right', 'value': {'expression': expr}}]}}})

    contribution.axes = sorted(axis_of)
    contribution.axis_type = axis_of

    # Value.
    if member.has_value:
      if aux:
        contribution.value_expr = rs.select.get('logica_value')
      else:
        contribution.value_expr = aggregated_expr
    self.RegisterExpressionRelations(contribution)
    return contribution

  def RegisterExpressionRelations(self, contribution):
    """Registers relations that are read only inside expressions.

    A relation mentioned solely within an aggregating expression (e.g.
    Sum{Empty(y)}) never shows up as a table read of the rule structure;
    find such calls and register them, so that the runtime loads their
    tables and treats their calls as reads."""
    names = set()

    def Collect(node):
      if isinstance(node, dict):
        if 'call' in node:
          names.add(node['call']['predicate_name'])
        for value in node.values():
          Collect(value)
      elif isinstance(node, list):
        for value in node:
          Collect(value)

    Collect(contribution.value_expr)
    Collect(contribution.constraints)
    Collect(list(contribution.definitions.values()))
    for name in sorted(names, key=str):
      if not isinstance(name, str) or name in self.relations:
        continue
      if (name.endswith(PORTAL_SUFFIX) or
          self.program.annotations.Ground(name) is not None):
        self.RelationOf(name, contribution.rule_text)

  # ------------------------------- Runtime -------------------------------

  def Run(self, sql_runner, progress=None):
    """Executes the plan: read inputs, iterate, write back portals."""
    try:
      import jax
    except ImportError:
      raise NeuralCompileException(
          'Neural execution requires JAX. Please run: '
          'python3 -m pip install jax', self.name)
    jax.config.update('jax_enable_x64', True)
    import jax.numpy as jnp
    import numpy as np

    # 1. Read input relations. Terminal runners return (header, rows),
    # notebook runners return a pandas DataFrame.
    input_data = {}
    for name, table in self.input_tables.items():
      result = sql_runner('SELECT * FROM %s' % table, self.engine,
                          is_final=True)
      if isinstance(result, tuple):
        header, rows = result
        input_data[name] = (list(header), [list(r) for r in rows])
      else:
        input_data[name] = (list(result.columns), result.values.tolist())

    # 2. Build domains: one per key type. Constant keys of the rules
    # participate even when no input relation mentions them.
    domain_values = {'Str': set(self.constant_keys['Str']),
                     'Num': set(self.constant_keys['Num'])}
    for name, (header, rows) in input_data.items():
      relation = self.relations[name]
      for row in rows:
        for field, field_type in zip(relation.key_fields,
                                     relation.key_types):
          value = row[header.index(self.FieldColumn(field))]
          domain_values[field_type].add(value)
    domains = {t: sorted(domain_values[t]) for t in domain_values}
    index = {t: {v: i for i, v in enumerate(domains[t])} for t in domains}
    domain_arrays = {
        'Num': jnp.array([float(v) for v in domains['Num']],
                         dtype=jnp.float64),
        'Str': None,  # Strings never participate in arithmetic.
    }

    def Dims(relation):
      return tuple(len(domains[t]) for t in relation.key_types)

    # 3. Tensors of input relations.
    tensors = {}
    for name, (header, rows) in input_data.items():
      relation = self.relations[name]
      mask = np.zeros(Dims(relation), dtype=bool)
      values = np.zeros(Dims(relation), dtype=np.float64)
      value_column = (header.index('logica_value')
                      if relation.has_value else None)
      for row in rows:
        position = tuple(
            index[t][row[header.index(self.FieldColumn(f))]]
            for f, t in zip(relation.key_fields, relation.key_types))
        mask[position] = True
        if value_column is not None:
          values[position] = float(row[value_column])
      tensors[name] = (jnp.array(mask), jnp.array(values))

    # 4. State: portals start empty.
    state = {}
    for member in self.members:
      portal = member.name + PORTAL_SUFFIX
      relation = Relation(portal, member.key_fields, member.key_types,
                          member.has_value)
      self.relations.setdefault(portal, relation)
      shape = Dims(relation)
      values = (jnp.full(shape, member.neutral, dtype=jnp.float64)
                if member.has_value else None)
      state[portal] = (jnp.zeros(shape, dtype=bool), values)

    runtime = Runtime(self, jnp, domains, domain_arrays, index)
    member_functions = [(m, runtime.MemberFunction(m)) for m in self.members]

    def Sweep(state, tensors):
      state = dict(state)
      for member, function in member_functions:
        state[member.name + PORTAL_SUFFIX] = function(state, tensors)
      return state

    sweep = jax.jit(Sweep)

    # 5. Iterate to stabilization.
    iterations = 0
    converged = False
    for iterations in range(1, self.repetitions + 1):
      new_state = sweep(state, tensors)
      if self.Converged(state, new_state, jnp):
        state = new_state
        converged = True
        break
      state = new_state
      if progress and iterations % 32 == 0:
        progress(iterations)

    # 6. Write the stabilized relations back into portal tables.
    for member in self.members:
      self.WriteBack(sql_runner, member,
                     state[member.name + PORTAL_SUFFIX], domains, np)

    return {'iterations': iterations, 'converged': converged}

  def FieldColumn(self, field):
    return 'col%d' % field if isinstance(field, int) else field

  def Converged(self, state, new_state, jnp):
    for name in state:
      old_mask, old_values = state[name]
      new_mask, new_values = new_state[name]
      if bool(jnp.any(old_mask != new_mask)):
        return False
      if old_values is None:
        continue
      both = old_mask & new_mask
      delta = jnp.where(both, jnp.abs(new_values - old_values), 0.0)
      if both.size and float(jnp.max(delta, initial=0.0)) > self.epsilon:
        return False
    return True

  def WriteBack(self, sql_runner, member, state_tensor, domains, np):
    """Writes a member's stabilized relation into its portal table."""
    mask, values = state_tensor
    mask = np.asarray(mask)
    if values is not None:
      values = np.asarray(values)
    positions = np.argwhere(mask)
    if not len(positions):
      return  # The portal table is already seeded empty.
    columns = [self.FieldColumn(f) for f in member.key_fields]
    if member.has_value:
      columns.append('logica_value')

    def SqlLiteral(value):
      if isinstance(value, str):
        return "'%s'" % value.replace("'", "''")
      return repr(value)

    integral_value = (member.has_value and
                      all(float(values[tuple(p)]).is_integer()
                          for p in positions))
    rows = []
    for position in positions:
      literals = [SqlLiteral(domains[t][i])
                  for t, i in zip(member.key_types, position)]
      if member.has_value:
        v = float(values[tuple(position)])
        literals.append(repr(int(v)) if integral_value else repr(v))
      rows.append('(%s)' % ', '.join(literals))
    sql = ('CREATE OR REPLACE TABLE %s AS '
           'SELECT * FROM (VALUES %s) AS t(%s)' % (
               member.table, ', '.join(rows), ', '.join(columns)))
    sql_runner(sql, self.engine, is_final=False)

  def __repr__(self):
    return 'NeuralPlan(%s: %s)' % (
        self.name, [m.name for m in self.members])


class Runtime(object):
  """Builds jnp closures from the compiled plan."""

  def __init__(self, plan, jnp, domains, domain_arrays, index):
    self.plan = plan
    self.jnp = jnp
    self.domains = domains
    self.domain_arrays = domain_arrays
    self.index = index

  def MemberFunction(self, member):
    """state, tensors -> (mask, values): the member's rewrite w_p."""
    jnp = self.jnp
    contribution_functions = [
        self.ContributionFunction(member, c) for c in member.contributions]
    combine = {'sum': jnp.add, 'min': jnp.minimum, 'max': jnp.maximum,
               'or': jnp.logical_or}[member.aggregation]

    def Evaluate(state, tensors):
      mask, values = None, None
      for function in contribution_functions:
        m, v = function(state, tensors)
        if mask is None:
          mask, values = m, v
        else:
          mask = mask | m
          if v is not None:
            values = combine(values, v)
      if member.has_value:
        values = jnp.where(mask, values, member.neutral)
      return mask, values

    return Evaluate

  def ContributionFunction(self, member, contribution):
    jnp = self.jnp

    def Evaluate(state, tensors):
      context = EvalContext(self, member, contribution,
                            contribution.axes, contribution.axis_type,
                            state, tensors)
      mask = jnp.array(True)
      for name, key_map, value_var in contribution.reads:
        relation = self.plan.relations[name]
        relation_mask, relation_values = context.Tensor(name)
        variables = [key_map[f] for f in relation.key_fields]
        mask = mask & context.Aligned(relation_mask, variables)
        if value_var is not None:
          context.environment[value_var] = context.Aligned(
              relation_values, variables)

      for variable, values in contribution.memberships:
        allowed = set(values)
        domain = self.domains[contribution.axis_type[variable]]
        vector = jnp.array([v in allowed for v in domain], dtype=bool)
        mask = mask & context.Aligned(vector, [variable])

      for constraint in contribution.constraints:
        mask = mask & context.EvalConstraint(constraint)

      if member.has_value:
        value, valid = context.Eval(contribution.value_expr)
        if valid is not True:
          mask = mask & valid
      else:
        value = None

      axis_sizes = context.AxisSizes()
      mask = jnp.broadcast_to(mask, axis_sizes) if axis_sizes else mask
      if value is not None:
        value = (jnp.broadcast_to(value, axis_sizes)
                 if axis_sizes else value)

      # Reduce onto member key axes.
      head_variables = {h[1] for h in contribution.head if h[0] == 'var'}
      reduce_axes = tuple(
          i for i, v in enumerate(contribution.axes)
          if v not in head_variables)
      # `initial` keeps reductions over empty axes well-defined.
      reduction = {
          'sum': lambda a, ax: jnp.sum(a, axis=ax),
          'min': lambda a, ax: jnp.min(a, axis=ax, initial=jnp.inf),
          'max': lambda a, ax: jnp.max(a, axis=ax, initial=-jnp.inf),
          'or': lambda a, ax: jnp.any(a, axis=ax)}[member.aggregation]
      if value is not None:
        masked_value = jnp.where(mask, value, member.neutral)
        value = (reduction(masked_value, reduce_axes)
                 if reduce_axes else masked_value)
      mask = jnp.any(mask, axis=reduce_axes) if reduce_axes else mask

      # Order remaining axes as member keys; insert one-hots for consts.
      kept = [v for v in contribution.axes if v in head_variables]
      target_order = [kept.index(h[1]) for h in contribution.head
                      if h[0] == 'var']
      mask = jnp.transpose(mask, target_order)
      if value is not None:
        value = jnp.transpose(value, target_order)

      for position, (kind, key) in enumerate(contribution.head):
        if kind != 'const':
          continue
        field_type = member.key_types[position]
        size = len(self.domains[field_type])
        i = self.index[field_type].get(key)
        one_hot = ((jnp.arange(size) == i) if i is not None
                   else jnp.zeros(size, dtype=bool))
        shape = [1] * (mask.ndim + 1)
        shape[position] = size
        one_hot = one_hot.reshape(shape)
        mask = jnp.expand_dims(mask, position) & one_hot
        if value is not None:
          value = jnp.where(one_hot, jnp.expand_dims(value, position),
                            member.neutral)
      if value is not None:
        value = jnp.where(mask, value, member.neutral)
      return mask, value

    return Evaluate


class EvalContext(object):
  """Evaluation of expression ASTs over a set of axes.

  Eval returns a pair (value, valid): valid is True or a boolean array;
  a row with an invalid value produces no derivation, mirroring the NULL
  produced in SQL by e.g. an inner aggregation over the empty set.
  """

  def __init__(self, runtime, member, contribution, axes, axis_type,
               state, tensors, parent=None):
    self.runtime = runtime
    self.jnp = runtime.jnp
    self.member = member
    self.contribution = contribution
    self.axes = list(axes)
    self.axis_type = dict(axis_type)
    self.axis_position = {v: i for i, v in enumerate(self.axes)}
    self.state = state
    self.tensors = tensors
    self.parent = parent
    self.environment = {}
    self.memo = {}

  def Tensor(self, name):
    if name in self.state:
      return self.state[name]
    return self.tensors[name]

  def AxisSizes(self):
    return tuple(len(self.runtime.domains[self.axis_type[v]])
                 for v in self.axes)

  def Aligned(self, array, variables):
    """Places an array whose dims correspond to `variables` into the full
    axes shape of this context."""
    jnp = self.jnp
    order = sorted(range(len(variables)),
                   key=lambda i: self.axis_position[variables[i]])
    array = jnp.transpose(array, order)
    shape = [1] * len(self.axes)
    for dim, i in enumerate(order):
      shape[self.axis_position[variables[i]]] = array.shape[dim]
    return array.reshape(shape)

  def FromParent(self, array):
    """Expands a parent-context array to this context's rank."""
    extra = len(self.axes) - len(self.parent.axes)
    return array.reshape(array.shape + (1,) * extra)

  def AxisValues(self, variable):
    domain = self.runtime.domain_arrays[self.axis_type[variable]]
    if domain is None:
      Error('String key used in arithmetic in rule of %s.' %
            color.Warn(self.member.name), self.contribution.rule_text)
    return self.Aligned(domain, [variable])

  def CombineValid(self, a, b):
    if a is True:
      return b
    if b is True:
      return a
    return a & b

  def Eval(self, node):
    """Expression AST -> (value array, valid)."""
    jnp = self.jnp
    literal = LiteralValue(node)
    if literal is not None:
      if isinstance(literal, str):
        Error('String values are outside of the neural fragment: %s.' %
              color.Warn(ExpressionText(node) or repr(literal)),
              self.contribution.rule_text)
      return jnp.array(float(literal), dtype=jnp.float64), True
    if IsVariable(node):
      return self.EvalVariable(VariableName(node), node)
    if isinstance(node, dict) and 'call' in node:
      return self.EvalCall(node['call'])
    if isinstance(node, dict) and 'combine' in node:
      return self.EvalCombine(node['combine'])
    if isinstance(node, dict) and 'implication' in node:
      return self.EvalImplication(node['implication'])
    Error('Expression %s is outside of the neural fragment.' %
          color.Warn(ExpressionText(node) or '<generated>'),
          self.contribution.rule_text)

  def EvalVariable(self, variable, node=None):
    variable = self.Canonical(variable)
    if variable in self.environment:
      return self.environment[variable], True
    if variable in self.axis_position:
      return self.AxisValues(variable), True
    if variable in self.contribution.definitions:
      if variable in self.memo:
        return self.memo[variable]
      result = self.Eval(self.contribution.definitions[variable])
      self.memo[variable] = result
      return result
    if self.parent is not None:
      value, valid = self.parent.EvalVariable(variable, node)
      return (self.FromParent(value),
              valid if valid is True else self.FromParent(valid))
    Error('Variable %s of a neural rule is not bound by any relation.' %
          color.Warn((node and ExpressionText(node)) or variable),
          self.contribution.rule_text)

  def EvalImplication(self, implication):
    """if-then-else chain, folded into elementwise selects.

    jnp.where(condition, a, b) is the ternary select; branches are tried
    in order and the first one whose condition is true and valid wins.
    An invalid condition (NULL in SQL) falls through to the next branch,
    exactly like CASE WHEN.
    """
    jnp = self.jnp
    value, valid = self.Eval(implication['otherwise'])
    for branch in reversed(implication['if_then']):
      condition, condition_valid = self.Eval(branch['condition'])
      consequence, consequence_valid = self.Eval(branch['consequence'])
      if condition_valid is not True:
        condition = condition & condition_valid
      value = jnp.where(condition, consequence, value)
      if consequence_valid is True and valid is True:
        valid = True
      else:
        broadcast = lambda v: (jnp.asarray(v) if v is True else v)
        valid = jnp.where(condition, broadcast(consequence_valid),
                          broadcast(valid))
    return value, valid

  def Canonical(self, variable):
    return self.contribution.canonical.Find(variable)

  def EvalCall(self, call):
    jnp = self.jnp
    op = call['predicate_name']
    if op == 'ValueOfUnnested':
      # A reference to an unnested variable is wrapped by rule_translate;
      # for a literal-list unnesting it is simply the axis variable.
      return self.Eval(FieldValues(call)[0])
    if op in self.runtime.plan.relations:
      return self.EvalRelationCall(call)
    argument_pairs = [self.Eval(a) for a in FieldValues(call)]
    arguments = [a for a, _ in argument_pairs]
    valid = True
    for _, v in argument_pairs:
      valid = self.CombineValid(valid, v)
    if op in ELEMENTWISE_OPS:
      return self.ApplyOp(op, arguments), valid
    if op in COMPARISON_OPS:
      operations = {
          '==': lambda a, b: a == b, '!=': lambda a, b: a != b,
          '<': lambda a, b: a < b, '<=': lambda a, b: a <= b,
          '>': lambda a, b: a > b, '>=': lambda a, b: a >= b}
      return operations[op](*arguments), valid
    if op in LOGICAL_OPS:
      if op == '!':
        return jnp.logical_not(arguments[0]), valid
      combine = (jnp.logical_and if op == '&&' else jnp.logical_or)
      result = arguments[0]
      for argument in arguments[1:]:
        result = combine(result, argument)
      return result, valid
    Error('Operation %s is outside of the neural fragment.' %
          color.Warn(op), self.contribution.rule_text)

  def EvalRelationCall(self, call):
    """A functional read of a relation inside an expression (combines)."""
    relation = self.runtime.plan.relations[call['predicate_name']]
    variables = []
    for fv in call['record']['field_value']:
      expression = fv['value']['expression']
      if not IsVariable(expression):
        Error('Neural relation reads inside aggregating expressions must '
              'use plain variables.',
              self.contribution.rule_text)
      variables.append(self.Canonical(VariableName(expression)))
    mask, values = self.Tensor(relation.name)
    if not relation.has_value:
      Error('Relation %s has no value to read.' %
            color.Warn(relation.name),
            self.contribution.rule_text)
    aligned_values = self.Aligned(values, variables) if variables else values
    aligned_mask = self.Aligned(mask, variables) if variables else mask
    return aligned_values, aligned_mask

  def EvalCombine(self, combine):
    """Inner aggregating expression: Sum{...}, Take{...}, etc."""
    jnp = self.jnp
    body = combine.get('body')
    if body and body.get('conjunction', {}).get('conjunct'):
      Error('Neural aggregating expressions with a body (Agg{x :- ...}) '
            'are not supported yet.',
            self.contribution.rule_text)
    [field_value] = combine['head']['record']['field_value']
    aggregation = field_value['value']['aggregation']['expression']
    op = aggregation['call']['predicate_name']
    inner = FieldValues(aggregation['call'])[0]

    # Local variables: arguments of relation reads not known to this
    # context become fresh axes of a child context.
    local_variables = []
    local_types = {}

    def CollectLocals(node):
      if isinstance(node, dict) and 'call' in node:
        call = node['call']
        if call['predicate_name'] in self.runtime.plan.relations:
          relation = self.runtime.plan.relations[call['predicate_name']]
          for fv in call['record']['field_value']:
            expression = fv['value']['expression']
            if not IsVariable(expression):
              continue
            variable = self.Canonical(VariableName(expression))
            if (self.KnowsVariable(variable) or
                variable in local_types):
              continue
            field = fv['field']
            field_type = relation.key_types[
                relation.key_fields.index(field)]
            local_variables.append(variable)
            local_types[variable] = field_type
      if isinstance(node, dict):
        for v in node.values():
          CollectLocals(v)
      elif isinstance(node, list):
        for v in node:
          CollectLocals(v)

    CollectLocals(inner)

    child_axis_type = dict(self.axis_type)
    child_axis_type.update(local_types)
    child = EvalContext(self.runtime, self.member, self.contribution,
                        self.axes + local_variables, child_axis_type,
                        self.state, self.tensors, parent=self)
    value, valid = child.Eval(inner)
    local_dims = tuple(range(len(self.axes),
                             len(self.axes) + len(local_variables)))
    full_shape = child.AxisSizes()
    if valid is True:
      valid = jnp.broadcast_to(jnp.array(True), full_shape)
    else:
      valid = jnp.broadcast_to(valid, full_shape)
    value = jnp.broadcast_to(value, full_shape)

    def Reduce(kind):
      """Reduces the group's values onto the outer axes."""
      neutral = NEUTRAL[kind]
      masked = jnp.where(valid, value, neutral)
      reduction = {
          'sum': lambda a, ax: jnp.sum(a, axis=ax),
          'min': lambda a, ax: jnp.min(a, axis=ax, initial=jnp.inf),
          'max': lambda a, ax: jnp.max(a, axis=ax, initial=-jnp.inf),
          'any': lambda a, ax: jnp.max(a, axis=ax, initial=-jnp.inf)}[kind]
      if local_dims:
        return (reduction(masked, local_dims),
                jnp.any(valid, axis=local_dims))
      return masked, valid

    if op in INNER_AGGREGATIONS:
      return Reduce(INNER_AGGREGATIONS[op])
    return self.EvalCustomAggregation(op, Reduce)

  def EvalCustomAggregation(self, op, Reduce):
    """Evaluates a user-defined aggregation via its defining rule.

    A definition like Take(x) = Coalesce(AnyValue(x), 0) is interpreted
    over the group: aggregation primitives applied to the argument become
    reductions, Coalesce chooses the first valid value, elementwise
    operations pass through.
    """
    jnp = self.jnp
    rules = [r for name, r in self.runtime.plan.program.rules if name == op]
    if len(rules) != 1:
      Error('Aggregation %s is outside of the neural fragment.' %
            color.Warn(op),
            self.contribution.rule_text)
    [rule] = rules
    fields = {fv['field']: fv['value'] for fv
              in rule['head']['record']['field_value']}
    if (set(fields) != {0, 'logica_value'} or
        not IsVariable(fields[0].get('expression', {}))):
      Error('Aggregation %s must be defined as F(x) = <expression of x>.' %
            color.Warn(op),
            self.contribution.rule_text)
    argument = VariableName(fields[0]['expression'])
    definition = fields['logica_value'].get('expression')
    if definition is None:
      Error('Aggregation %s has no value definition.' %
            color.Warn(op),
            self.contribution.rule_text)

    def EvalDefinition(node):
      """(value, valid) of the definition body over outer axes."""
      literal = LiteralValue(node)
      if literal is not None:
        return jnp.array(float(literal), dtype=jnp.float64), True
      if IsVariable(node):
        Error('Aggregation %s uses its argument outside of an aggregating '
              'primitive.' % color.Warn(op),
              self.contribution.rule_text)
      if isinstance(node, dict) and 'call' in node:
        call = node['call']
        name = call['predicate_name']
        arguments = FieldValues(call)
        if name in INNER_AGGREGATIONS:
          if not (len(arguments) == 1 and IsVariable(arguments[0]) and
                  VariableName(arguments[0]) == argument):
            Error('Aggregation primitive %s in %s must be applied to the '
                  'aggregated argument.' %
                  (color.Warn(name), color.Warn(op)),
                  self.contribution.rule_text)
          return Reduce(INNER_AGGREGATIONS[name])
        pairs = [EvalDefinition(a) for a in arguments]
        if name == 'Coalesce':
          value, valid = pairs[-1]
          for v, ok in reversed(pairs[:-1]):
            if ok is True:
              value, valid = v, True
            else:
              value = jnp.where(ok, v, value)
              valid = ok | valid if valid is not True else True
          return value, valid
        values = [v for v, _ in pairs]
        valid = True
        for _, ok in pairs:
          valid = self.CombineValid(valid, ok)
        if name in ELEMENTWISE_OPS:
          return self.ApplyOp(name, values), valid
        Error('Operation %s in aggregation %s is outside of the neural '
              'fragment.' % (color.Warn(name), color.Warn(op)),
              self.contribution.rule_text)
      Error('Aggregation %s definition is outside of the neural '
            'fragment.' % color.Warn(op),
            self.contribution.rule_text)

    return EvalDefinition(definition)

  def KnowsVariable(self, variable):
    if (variable in self.environment or variable in self.axis_position or
        variable in self.contribution.definitions):
      return True
    return self.parent.KnowsVariable(variable) if self.parent else False

  def EvalConstraint(self, constraint):
    """Comparison AST -> boolean mask over this context's axes."""
    jnp = self.jnp
    call = constraint.get('call')
    if not call or call['predicate_name'] not in (COMPARISON_OPS |
                                                  LOGICAL_OPS):
      Error('Only comparisons and logical operations may constrain '
            'neural rules; found %s.' %
            color.Warn((call and call['predicate_name']) or
                       ExpressionText(constraint) or '<generated>'),
            self.contribution.rule_text)
    op = call['predicate_name']
    if op in LOGICAL_OPS:
      result, valid = self.EvalCall(call)
      return result if valid is True else result & valid
    left_node, right_node = FieldValues(call)

    def StringAxis(node):
      if IsVariable(node):
        v = self.Canonical(VariableName(node))
        if (v in self.axis_position and self.axis_type[v] == 'Str'):
          return v
      return None

    operations = {
        '==': lambda a, b: a == b, '!=': lambda a, b: a != b,
        '<': lambda a, b: a < b, '<=': lambda a, b: a <= b,
        '>': lambda a, b: a > b, '>=': lambda a, b: a >= b}

    left_axis, right_axis = StringAxis(left_node), StringAxis(right_node)
    if left_axis or right_axis:
      # The domain is sorted, so index order coincides with the
      # lexicographic order of the strings: comparisons act on indices
      # (axis vs axis) or on a precomputed boolean vector (axis vs
      # literal).
      size = len(self.runtime.domains['Str'])
      if left_axis and right_axis:
        positions = jnp.arange(size)
        return operations[op](self.Aligned(positions, [left_axis]),
                              self.Aligned(positions, [right_axis]))
      axis = left_axis or right_axis
      literal_node = right_node if left_axis else left_node
      literal = LiteralValue(literal_node)
      if not isinstance(literal, str):
        Error('String keys can only be compared with string literals or '
              'other keys.',
              self.contribution.rule_text)
      compare = operations[op]
      vector = jnp.array(
          [bool(compare(value, literal)) if left_axis
           else bool(compare(literal, value))
           for value in self.runtime.domains['Str']], dtype=bool)
      return self.Aligned(vector, [axis])

    (left, left_valid), (right, right_valid) = (
        self.Eval(left_node), self.Eval(right_node))
    result = operations[op](left, right)
    valid = self.CombineValid(left_valid, right_valid)
    return result if valid is True else result & valid

  def ApplyOp(self, op, arguments):
    jnp = self.jnp
    if op == '+':
      return arguments[0] + arguments[1]
    if op == '-':
      return (arguments[0] - arguments[1] if len(arguments) == 2
              else -arguments[0])
    if op == '*':
      return arguments[0] * arguments[1]
    if op == '/':
      return arguments[0] / arguments[1]
    if op == '^':
      return arguments[0] ** arguments[1]
    if op == 'Least':
      result = arguments[0]
      for a in arguments[1:]:
        result = jnp.minimum(result, a)
      return result
    if op == 'Greatest':
      result = arguments[0]
      for a in arguments[1:]:
        result = jnp.maximum(result, a)
      return result
    unary = {'Abs': jnp.abs, 'Exp': jnp.exp, 'Log': jnp.log,
             'Sqrt': jnp.sqrt, 'Sin': jnp.sin, 'Cos': jnp.cos,
             'Floor': jnp.floor}
    return unary[op](arguments[0])
