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

"""Neural execution of Logica: tensor recursion and learning.

Two annotations turn parts of a Logica program into JAX tensor programs:

  * @Recursive(P, mode: "neural") iterates the recursive cover of P as a
    jitted tensor computation instead of a SQL loop;
  * @NeuralTarget(Loss, learn: [W]) trains the predicates W by gradient
    descent of the scalar Loss; the rules of W serve as initialization,
    and after training every reader of W sees the learned relation.

Both rest on the same translation. A rule with an aggregation is a
masked contraction: string and numeric keys are indexed into dense axes,
every relation becomes a pair of arrays (support mask, values), a rule
contribution becomes broadcast + elementwise operations + a reduction in
the semiring of its aggregation (+= / Min= / Max=; a functional = rule
derives one value per key, which the runtime verifies). A recursive
cover iterates its rewrite to stabilization; a learning cone evaluates
feed-forward, iterating recursion loops inside it with a gradient
through a scan of the stabilization depth.

The file is ordered the way a program lives through it:

  1. before recursion unfolding, while every predicate bears its own
     name, the original rules are analyzed: columns are partitioned into
     join-classes (each class is a tensor axis with its own numbering of
     values and its own type), learning cones are condensed into
     components, and @NeuralTarget programs are rewritten;
  2. after @Make, input relations of neural iterations are grounded;
  3. after type inference, plans are compiled and attached to the
     executions' iterations; concertina runs a plan when it reaches the
     iteration, and the plan writes its results into the same tables the
     SQL loop would have written.

Semantics mirrors the SQL engine: an empty inner aggregation is the SQL
NULL — a validity mask flowing through expressions; an `if` with an
invalid condition falls to else exactly like CASE WHEN; conflicting =
definitions are reported. Sum-of-product contractions compile to einsum
and never materialize the cube of rule variables.

Set LOGICA_NEURAL_TRACE=1 to print the loss and gradient norms of
training at power-of-two steps.
"""

import collections
import copy
import math
import os
import re

if '.' not in __package__:
  from common import color
  from compiler import rule_translate
  from parser_py import parse
  from type_inference.research import reference_algebra
else:
  from ..common import color
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


# ========================= Expression tree helpers ========================

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


# ==================== Before unfolding: column classes ====================

class ColumnClasses(object):
  """Join-equivalence classes of predicate columns.

  Extracted from the original rules before recursion unfolding: a rule
  variable binding two columns (in reads or between a read and a head
  position), an equality or a comparison between two variables — all
  unite the columns' classes. Every class receives its own numbering of
  values (its own tensor axis) and, later, its own type.

  Functional predicates (Clip, ToString wrappers and alike) are macro
  parameters, not tensor axes: they are excluded, otherwise a helper
  called with pixels here and examples there would glue unrelated axes
  together."""

  def __init__(self):
    self.union = UnionFind()
    self.known_columns = set()

  def ColumnNode(self, predicate, field):
    return ('column', FamilyOrigin(predicate), field)

  def UniteColumnWithVariable(self, predicate, field, variable_node):
    self.known_columns.add((predicate, field))
    self.union.Union(self.ColumnNode(predicate, field), variable_node)

  def OfColumn(self, predicate, field):
    """Class of a column; phases of a family carry the family's columns."""
    return self.union.Find(self.ColumnNode(predicate, field))

  def __repr__(self):
    by_root = collections.defaultdict(list)
    for predicate, field in sorted(self.known_columns, key=str):
      by_root[self.OfColumn(predicate, field)].append(
          '%s.%s' % (predicate, field))
    return 'ColumnClasses(%s)' % '; '.join(
        '{%s}' % ', '.join(columns) for columns in by_root.values())


MACHINERY_SUFFIXES = ['_portal', '_diamond', '_init', '_before',
                      '_fixpoint']


def OriginPredicate(name):
  """The original predicate whose columns an unfolding artifact carries."""
  if AUX_MARKER in name:
    return name[:name.index(AUX_MARKER)]
  if '_ROne' in name:
    return name[:name.index('_ROne')]
  if '_RZero' in name:
    return name[:name.index('_RZero')]
  for suffix in MACHINERY_SUFFIXES:
    if name.endswith(suffix):
      return name[:-len(suffix)]
  return name


PHASE_PATTERN = re.compile(
    r'^(?P<base>.*?)_(?P<phase>diamond|portal)(?P<family>(?:_f\d+)*)$')


def ParsePhase(name):
  """(base, phase, family) of an unfolding-phase name.

  The unfolder derives phase names from the predicate name (X_diamond,
  X_portal), and functors append _fN to the names they copy — nothing
  runs after functors that would rename, so the shape of the name is a
  stable output format of the last two transformations. X_diamond ->
  (X, 'diamond', ''); X_portal_f3 -> (X, 'portal', '_f3'); a name with
  no phase parses as (name, None, '')."""
  match = PHASE_PATTERN.match(name)
  if not match:
    return name, None, ''
  return match.group('base'), match.group('phase'), match.group('family')


def FamilyOrigin(name):
  """The relation whose column classes a phase name carries.

  X_portal is always logically X: diamond and portal are phases of the
  final predicate of their family. X_diamond_f3 and X_portal_f3 are
  phases of the f3 functor copy — the copy's own family, with its own
  axes."""
  base, phase, family = ParsePhase(name)
  if phase is None:
    return name
  return base + family


def ProgramIsNeural(rules):
  """Whether the program uses neural execution at all."""
  for rule in rules:
    head = rule['head']['predicate_name']
    if head == '@NeuralTarget':
      return True
    if head == '@Recursive':
      for field_value in rule['head']['record']['field_value']:
        if (field_value['field'] == 'mode' and
            LiteralValue(field_value['value']['expression']) == 'neural'):
          return True
  return False


def ExtractColumnClasses(rules):
  """Extracts column classes of the program's rules.

  Runs on the final program — recursion unfolded, functors applied: the
  machinery reads are physical there (the final pass reads the diamond,
  the diamond reads the portal), so the join structure glues through
  live rule variables, and phases funnel onto their family's final name
  by FamilyOrigin. Functor copies are self-contained families with
  their own axes. Returns an empty structure for programs without
  neural execution."""
  classes = ColumnClasses()
  if not ProgramIsNeural(rules):
    return classes

  rules_of = collections.defaultdict(list)
  for rule in rules:
    head = rule['head']['predicate_name']
    if head[0] != '@':
      rules_of[head].append(rule)
  functional = {p for p in rules_of if IsFunctional(p, rules_of)}

  rule_counter = [0]

  def WalkRule(rule, head_bridge, stack):
    """Glues one rule's structure into the classes.

    head_bridge is None for an ordinary rule — its head positions are
    registered as columns. For the rule of a functional predicate walked
    at a call site, head_bridge maps head fields to the caller's
    variable nodes: the functional is injected into the caller, so its
    head columns are macro parameters, not tensor axes, and its body
    glues through the bridge. A fresh scope per call site keeps
    unrelated call sites unglued."""
    head_name = rule['head']['predicate_name']
    rule_counter[0] += 1
    scope = rule_counter[0]
    allocator = rule_translate.NamesAllocator()
    try:
      rs = rule_translate.ExtractRuleStructure(rule, allocator, None)
      rs.ElliminateInternalVariables(assert_full_ellimination=False)
    except rule_translate.RuleCompileException:
      return  # SQL compilation will report this rule properly.

    def VariableNode(variable):
      return ('variable', scope, variable)

    # Reads bind columns to variables.
    for (alias, field), variable in rs.vars_map.items():
      if alias is None or field == 'logica_value':
        continue
      predicate = rs.tables[alias]
      if predicate == '=':
        continue
      if predicate in functional:
        continue
      classes.UniteColumnWithVariable(predicate, field,
                                      VariableNode(variable))
    # The two sides of the `=` pseudo-relation are equal.
    equality_sides = collections.defaultdict(dict)
    for (alias, field), variable in rs.vars_map.items():
      if alias is not None and rs.tables[alias] == '=':
        equality_sides[alias][field] = variable
    for sides in equality_sides.values():
      classes.union.Union(VariableNode(sides['left']),
                          VariableNode(sides['right']))
    # Head positions are written by variables; an injected functional
    # bridges them to the caller's arguments instead.
    for field, expression in rs.select.items():
      if field == 'logica_value':
        continue
      if IsVariable(expression):
        node = VariableNode(VariableName(expression))
        if head_bridge is None:
          classes.UniteColumnWithVariable(head_name, field, node)
        elif field in head_bridge:
          classes.union.Union(head_bridge[field], node)
    # Explicit equalities and comparisons between variables.
    def UniteComparedVariables(node):
      if isinstance(node, dict) and 'call' in node:
        call = node['call']
        if call['predicate_name'] in COMPARISON_OPS:
          arguments = FieldValues(call)
          if (len(arguments) == 2 and IsVariable(arguments[0]) and
              IsVariable(arguments[1])):
            classes.union.Union(
                VariableNode(VariableName(arguments[0])),
                VariableNode(VariableName(arguments[1])))
      if isinstance(node, dict):
        for value in node.values():
          UniteComparedVariables(value)
      elif isinstance(node, list):
        for value in node:
          UniteComparedVariables(value)
    UniteComparedVariables(rs.constraints)
    for unification in rs.vars_unification:
      if (IsVariable(unification['left']) and
          IsVariable(unification['right'])):
        classes.union.Union(
            VariableNode(VariableName(unification['left'])),
            VariableNode(VariableName(unification['right'])))
    # Relation reads inside aggregating expressions.
    def UniteCombineReads(node):
      if isinstance(node, dict) and 'call' in node:
        call = node['call']
        name = call['predicate_name']
        if name in rules_of and name not in functional:
          for field_value in call['record']['field_value']:
            expression = field_value['value']['expression']
            if IsVariable(expression):
              classes.UniteColumnWithVariable(
                  name, field_value['field'],
                  VariableNode(VariableName(expression)))
      if isinstance(node, dict):
        for value in node.values():
          UniteCombineReads(value)
      elif isinstance(node, list):
        for value in node:
          UniteCombineReads(value)
    UniteCombineReads(rs.select)
    UniteCombineReads(rs.vars_unification)
    UniteCombineReads(rs.constraints)
    # Functional predicates are injected into their callers: walk their
    # rules per expression call site with the head-to-arguments bridge.
    def ExpandFunctionalCalls(node):
      if isinstance(node, dict):
        if 'call' in node:
          call = node['call']
          name = call['predicate_name']
          if name in functional and name not in stack:
            bridge = {}
            for field_value in call['record']['field_value']:
              expression = field_value['value']['expression']
              if IsVariable(expression):
                bridge[field_value['field']] = VariableNode(
                    VariableName(expression))
            for functional_rule in rules_of[name]:
              WalkRule(functional_rule, bridge, stack | {name})
        for value in node.values():
          ExpandFunctionalCalls(value)
      elif isinstance(node, list):
        for value in node:
          ExpandFunctionalCalls(value)
    ExpandFunctionalCalls(rs.select)
    ExpandFunctionalCalls(rs.vars_unification)
    ExpandFunctionalCalls(rs.constraints)
    # A functional read as a body conjunct bridges through vars_map.
    for alias, predicate in rs.tables.items():
      if predicate in functional and predicate not in stack:
        bridge = {}
        for (a, field), variable in rs.vars_map.items():
          if a == alias and field != 'logica_value':
            bridge[field] = VariableNode(variable)
        for functional_rule in rules_of[predicate]:
          WalkRule(functional_rule, bridge, stack | {predicate})

  for rule in rules:
    head_name = rule['head']['predicate_name']
    if head_name[0] == '@' or head_name in functional:
      continue
    WalkRule(rule, None, set())
  return classes

# ==================== Before unfolding: learning cones ====================

def NeuralTargetAnnotations(rules):
  """[(target, learned predicates)] of the @NeuralTarget annotations."""
  targets = []
  for rule in rules:
    if rule['head']['predicate_name'] != '@NeuralTarget':
      continue
    fields = {fv['field']: fv['value']['expression']
              for fv in rule['head']['record']['field_value']}
    target = fields[0]['literal']['the_predicate']['predicate_name']
    if 'learn' not in fields:
      Error('@NeuralTarget must specify learn: [...] with the predicates '
            'to train.', target)
    learn = [e['literal']['the_predicate']['predicate_name']
             for e in fields['learn']['literal']['the_list']['element']]
    targets.append((target, learn))
  return targets


def ExtractNeuralComponents(dependencies):
  """Extracts the components of every learning cone.

  Runs before recursion unfolding, while recursion is still visible as
  dependency cycles; `dependencies` is the functors.Functors object of
  the original rules. The cone of @NeuralTarget(Loss, learn: [W]) —
  every predicate on a path from W to Loss — is condensed into
  components: single predicates and recursion loops (strongly connected
  components), listed in evaluation order. The training plan later
  assembles itself from these components.

  Returns: target -> [('single', name) | ('loop', [names])]."""
  return {target: ConeComponents(dependencies, target, learn)
          for target, learn in NeuralTargetAnnotations(dependencies.rules)}


def ConeComponents(dependencies, target, learn):
  """Components of one learning cone, dependencies first."""
  learned = set(learn)

  def DependsOnLearned(p):
    return bool(learned & set(dependencies.args_of.get(p, [])))

  def DirectDependencies(p):
    """Direct dependencies, looking through multi-body auxiliaries:
    an auxiliary is the inside of its parent, not a member itself."""
    result = []
    for d in dependencies.direct_args_of.get(p, []):
      if AUX_MARKER in d:
        result.extend(DirectDependencies(d))
      else:
        result.append(d)
    return result

  if not DependsOnLearned(target):
    Error('Target %s does not depend on the learned predicates %s.' %
          (color.Warn(target), sorted(learned)), target)

  cone = set()
  stack = [target]
  while stack:
    p = stack.pop()
    if p in cone:
      continue
    cone.add(p)
    for d in DirectDependencies(p):
      if d not in learned and d not in cone and DependsOnLearned(d):
        stack.append(d)

  # Tarjan's strongly connected components over the cone subgraph;
  # Tarjan emits components in reverse topological order, so the result
  # is dependencies-first once built bottom-up.
  index_of = {}
  lowlink = {}
  on_stack = set()
  stack = []
  components = []
  counter = [0]

  def Edges(p):
    return [d for d in sorted(DirectDependencies(p)) if d in cone]

  def Connect(p):
    index_of[p] = lowlink[p] = counter[0]
    counter[0] += 1
    stack.append(p)
    on_stack.add(p)
    for d in Edges(p):
      if d not in index_of:
        Connect(d)
        lowlink[p] = min(lowlink[p], lowlink[d])
      elif d in on_stack:
        lowlink[p] = min(lowlink[p], index_of[d])
    if lowlink[p] == index_of[p]:
      component = []
      while True:
        q = stack.pop()
        on_stack.remove(q)
        component.append(q)
        if q == p:
          break
      if len(component) == 1 and component[0] not in Edges(component[0]):
        components.append(('single', component[0]))
      else:
        components.append(('loop', sorted(component)))

  for p in sorted(cone):
    if p not in index_of:
      Connect(p)
  return components


def RewriteNeuralTargets(rules):
  """Rewrites @NeuralTarget(Loss, learn: [W]) programs.

  The rules of every learned predicate W become W_init — its
  initialization, computed by ordinary SQL into a stored table. W itself
  becomes a stored copy of W_init whose table the training plan
  overwrites with the learned values; every reader of W thus sees the
  trained relation. A one-shot @Iteration drives the plan through
  concertina."""
  targets = NeuralTargetAnnotations(rules)
  if not targets:
    return rules

  owner = {}
  for target, learn in targets:
    for predicate in learn:
      if predicate in owner:
        Error('Predicate %s is learned by both %s and %s; a learned '
              'predicate must have a single target.' %
              (color.Warn(predicate), color.Warn(owner[predicate]),
               color.Warn(target)), predicate)
      owner[predicate] = target

  head_records = {}
  for rule in rules:
    head = rule['head']['predicate_name']
    if head in owner:
      rule['head']['predicate_name'] = head + '_init'
      head_records.setdefault(head, rule['head']['record'])

  def CopyRule(predicate):
    """predicate(k0, name: k1, ...) = predicate_init(k0, name: k1, ...)."""
    if predicate not in head_records:
      Error('Learned predicate %s has no rules; its rules define its '
            'initialization.' % color.Warn(predicate), predicate)
    arguments = []
    for field_value in head_records[predicate]['field_value']:
      field = field_value['field']
      if field == 'logica_value':
        continue
      if isinstance(field, int):
        arguments.append('key_%d' % field)
      else:
        arguments.append('%s: key_%s' % (field, field))
    signature = ', '.join(arguments)
    return '%s(%s) = %s_init(%s);' % (
        predicate, signature, predicate, signature)

  extra_rules = []
  for target, learn in targets:
    for predicate in learn:
      extra_rules.append('@Ground(%s_init);' % predicate)
      extra_rules.append(CopyRule(predicate))
      extra_rules.append('@Ground(%s);' % predicate)
    extra_rules.append(
        '@Iteration(%s_neural_target, predicates: [%s], repetitions: 1, '
        'mode: "diamond", neural_target: %s);' % (
            target, ', '.join(learn), target))
  return rules + parse.ParseFile('\n'.join(extra_rules))['rule']


# ==================== After @Make: grounding of inputs ====================

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
    # Combine-local variables (Sum{...}) are bound by their own group,
    # not by the rule body: they must not make the predicate functional.
    select_vars = set(rule_translate.AllMentionedVariables(
        rs.select, dive_in_combines=False))
    if select_vars - BoundVariables(rs):
      return True
  return False


def AppendAutoGrounds(rules, dependencies):
  """Grounds input relations of neural iterations and neural targets, so
  that the neural runtime can read them from tables.

  `dependencies` is the functors.Functors object of the program: it
  already knows what depends on what (direct_args_of / args_of)."""
  neural_iterations = []
  target_iterations = []
  for rule in rules:
    if rule['head']['predicate_name'] != '@Iteration':
      continue
    fields = {fv['field']: fv['value']['expression']
              for fv in rule['head']['record']['field_value']}
    if 'neural' in fields and LiteralValue(fields['neural']) is True:
      neural_iterations.append(fields)
    if 'neural_target' in fields:
      target_iterations.append(fields)
  if not neural_iterations and not target_iterations:
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

  def IterationPredicates(fields):
    return [e['literal']['the_predicate']['predicate_name']
            for e in fields['predicates']['literal']['the_list']['element']]

  candidates = set()

  for fields in neural_iterations:
    diamond_predicates = IterationPredicates(fields)
    members = {p[:-len(DIAMOND_SUFFIX)] for p in diamond_predicates
               if p.endswith(DIAMOND_SUFFIX)}
    frontier = list(diamond_predicates)
    seen = set(frontier)
    while frontier:
      p = frontier.pop()
      for name in dependencies.direct_args_of.get(p, []):
        if name in seen:
          continue
        seen.add(name)
        if AUX_MARKER in name:
          frontier.append(name)
          continue
        if (name in members or name[0] == '@' or
            ParsePhase(name)[1] is not None or name.endswith('_RZero') or
            '_ROne' in name):
          continue
        if name not in rules_of:
          continue  # Built-in or external table.
        if IsFunctional(name, rules_of):
          frontier.append(name)  # Injected into callers: walk through.
          continue
        candidates.add(name)

  for fields in target_iterations:
    learn = set(IterationPredicates(fields))
    target = fields['neural_target']['literal']['the_predicate'][
        'predicate_name']

    def DependsOnLearned(p):
      return bool(learn & set(dependencies.args_of.get(p, [])))

    frontier = [target]
    seen = set(frontier)
    while frontier:
      p = frontier.pop()
      for name in dependencies.direct_args_of.get(p, []):
        if name in seen:
          continue
        seen.add(name)
        if name in learn or name[0] == '@' or name.endswith('_init'):
          continue
        if name not in rules_of:
          continue  # Built-in or external table.
        if DependsOnLearned(name) or IsFunctional(name, rules_of):
          frontier.append(name)  # Inside the cone or injected: walk through.
        else:
          candidates.add(name)   # An input of the cone.

  for name in sorted(candidates):
    if name in grounded or IsFunctional(name, rules_of):
      continue
    rules.extend(parse.ParseFile('@Ground(%s);' % name)['rule'])


def RenamePredicates(node, mapping):
  """Renames predicate references of an AST node in place."""
  if isinstance(node, dict):
    name = node.get('predicate_name')
    if name in mapping:
      node['predicate_name'] = mapping[name]
    for value in node.values():
      RenamePredicates(value, mapping)
  elif isinstance(node, list):
    for value in node:
      RenamePredicates(value, mapping)


def AnnotationSubjectName(rule):
  """Predicate name of an annotation's first argument, or None."""
  try:
    return rule['head']['record']['field_value'][0]['value'][
        'expression']['literal']['the_predicate']['predicate_name']
  except (KeyError, IndexError, TypeError):
    return None


def CompleteFunctorIslands(rules):
  """Completes functor copies of neural recursion islands.

  A functor copies what the rules show: the diamonds of a neural
  recursion (the final pass reads them, so they are in the cone) — but
  not the @Iteration that runs them, whose subject heads no rule, and
  not the portal state, whose connection to the diamonds lives in the
  execution plan. The copy is completed here from the names:
  X_diamond<family> can only be a functor copy of X_diamond, and
  X_portal is always logically X. A mutually recursive cover is a
  strongly connected component, so a family copies an island whole or
  not at all.

  For every copied family this reroutes the family's portal reads and
  diamond @Grounds onto the family's own portals, clones the portals'
  typed seed rules and @Grounds, and clones the original @Iteration
  with the family's names."""
  rules_of = collections.defaultdict(list)
  for rule in rules:
    rules_of[rule['head']['predicate_name']].append(rule)

  # Diamond -> its (neural) @Iteration rule.
  iteration_of = {}
  for iteration_rule in rules_of.get('@Iteration', []):
    fields = {fv['field']: fv['value']['expression']
              for fv in iteration_rule['head']['record']['field_value']}
    if LiteralValue(fields.get('neural', {})) is not True:
      continue
    for element in fields.get('predicates', {}).get(
        'literal', {}).get('the_list', {}).get('element', []):
      name = element.get('literal', {}).get(
          'the_predicate', {}).get('predicate_name')
      if name:
        iteration_of[name] = iteration_rule

  # (family, id of the original iteration) -> copied diamond bases.
  copies = collections.defaultdict(set)
  iteration_by_id = {}
  for head in list(rules_of):
    base, phase, family = ParsePhase(head)
    if phase != 'diamond' or not family:
      continue
    original = iteration_of.get(base + DIAMOND_SUFFIX)
    if original is None:
      continue  # Not a neural island (e.g. a classic recursion copy).
    iteration_by_id[id(original)] = original
    copies[family, id(original)].add(base)

  new_rules = []
  for (family, iteration_id), bases in sorted(
      copies.items(), key=lambda item: (item[0][0], sorted(item[1]))):
    original = iteration_by_id[iteration_id]
    island = {ParsePhase(d)[0] for d in iteration_of
              if iteration_of[d] is original}
    if bases != island:
      Error('Functor copied only part of recursion island %s: %s.' %
            (color.Warn(', '.join(sorted(island))),
             color.Warn(', '.join(sorted(bases)))), str(sorted(bases)))
    portal_map = {b + PORTAL_SUFFIX: b + PORTAL_SUFFIX + family
                  for b in island}
    diamond_map = {b + DIAMOND_SUFFIX: b + DIAMOND_SUFFIX + family
                   for b in island}
    # Family rules read the family's own state. Portal reads live only
    # in diamond rules and their copied auxiliaries — all of which bear
    # the family suffix.
    for head in rules_of:
      if head[0] != '@' and head.endswith(family):
        for rule in rules_of[head]:
          RenamePredicates(rule, portal_map)
    # The copied diamonds' @Ground reroutes into the family's portals.
    for ground_rule in rules_of.get('@Ground', []):
      if AnnotationSubjectName(ground_rule) in diamond_map.values():
        RenamePredicates(ground_rule, portal_map)
    for b in sorted(island):
      # The portal: its typed seed rule and its @Ground.
      for seed in rules_of[b + PORTAL_SUFFIX]:
        clone = copy.deepcopy(seed)
        clone['head']['predicate_name'] = b + PORTAL_SUFFIX + family
        new_rules.append(clone)
      new_rules.extend(parse.ParseFile(
          '@Ground(%s);' % (b + PORTAL_SUFFIX + family))['rule'])
    # The iteration, renamed onto the family.
    iteration_clone = copy.deepcopy(original)
    subject = iteration_clone['head']['record']['field_value'][0][
        'value']['expression']['literal']['the_predicate']
    subject['predicate_name'] = subject['predicate_name'] + family
    RenamePredicates(iteration_clone, diamond_map)
    new_rules.append(iteration_clone)
  rules.extend(new_rules)


def CheckNeuralPredicatesIterate(annotations):
  """Neural mode of a non-recursive predicate would be silently ignored;
  telling the user instead."""
  requested = {
      p for p, entry in annotations.annotations.get('@Recursive', {}).items()
      if entry.get('mode') == 'neural'}
  if not requested:
    return
  covered = set()
  for args in annotations.annotations.get('@Iteration', {}).values():
    neural, _ = IterationPlanKind(args)
    if neural:
      covered |= {p['predicate_name'][:-len(DIAMOND_SUFFIX)]
                  for p in args['predicates']
                  if p['predicate_name'].endswith(DIAMOND_SUFFIX)}
  for p in sorted(requested - covered):
    Error('Predicate %s requests neural recursion, but it is not '
          'recursive. Neural execution iterates a recursive predicate to '
          'stabilization, so %s must depend on itself (directly or '
          'through other predicates).' % (color.Warn(p), color.Warn(p)), p)


# ======================= After type inference: plans ======================

def IterationPlanKind(args):
  """(neural, target) marks of an @Iteration's raw annotation."""
  target = args.get('neural_target')
  if isinstance(target, dict):
    target = target.get('predicate_name')
  return bool(args.get('neural')), target


def CompilePlans(program):
  """Compiles the plan of every neural iteration of the program.

  An @Iteration marked neural: true (tensor recursion) or neural_target
  (learning) executes as a single Python plan; concertina runs the plan
  when it reaches the iteration. A plan is a pure function of the
  program — its rules, annotations, inferred types and cone components —
  so plans are compiled once, right after type inference."""
  plans = {}
  iteration_annotations = program.annotations.annotations.get(
      '@Iteration', {})
  for name, iteration in program.annotations.Iterations().items():
    neural, target = IterationPlanKind(iteration_annotations.get(name, {}))
    if target:
      plans[name] = NeuralTargetPlan(program, name, iteration, target)
    elif neural:
      plans[name] = NeuralPlan(program, name, iteration)
  return plans


def AttachPlans(plans, iterations):
  """Points each iteration at its compiled plan."""
  for name, iteration in iterations.items():
    if name in plans:
      iteration['plan'] = plans[name]
      # A learning loop is scheduled as a one-repetition iteration, but
      # its plan runs up to `steps` training steps: show those in the
      # progress display.
      steps = getattr(plans[name], 'steps', None)
      if steps:
        iteration['repetitions'] = steps


def AddLearningLoopDependencies(execution, translator):
  """Adds the in-edges of collapsed learning loops.

  Recursive plans need no help: their loop body is also compiled into
  the diamond SQL actions, which naturally depend on every table the
  loop reads. A learning loop is different: its scheduled action is the
  plain copy W = W_init, silent about the data of the objective, while
  the loop also consumes that data. Those in-edges are added here. For
  a learned predicate W the initialization table W_init is read instead
  of W itself: W is the loop's own output."""
  for iteration in execution.iterations.values():
    plan = iteration.get('plan')
    if plan is None or getattr(plan, 'target', None) is None:
      continue
    learned = set(plan.learned)
    for input_name in plan.input_tables:
      input_action = (input_name + '_init'
                      if input_name in learned else input_name)
      translator.TranslateTable(input_action, None, edge_needed=False)
      for plan_action in iteration['predicates']:
        if input_action != plan_action:
          # An edge (a, b) means: b depends on a. The plan runs when
          # concertina reaches any action of its iteration, so every one
          # of them must wait for every input table.
          execution.dependency_edges.append((input_action, plan_action))


# ======================== The tensor program model ========================

class Relation(object):
  """A relation participating in the tensor program."""

  def __init__(self, name, key_fields, key_types, has_value):
    self.name = name
    self.key_fields = key_fields  # Field names in table column order.
    self.key_types = key_types    # Column class per key field.
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
    self.canonical = None       # UnionFind of the rule's variables.
    self.rule_text = ''

  def __repr__(self):
    return 'Contribution(axes: %s, reads: %s)' % (self.axes, self.reads)


class Member(object):
  """A cover member: its key signature and rule contributions."""

  def __init__(self, name, diamond_name):
    self.name = name
    self.diamond_name = diamond_name
    # The state relation this member's rules read and write: the family's
    # portal (X_portal of X_diamond, X_portal_f3 of X_diamond_f3).
    base, phase, family = ParsePhase(diamond_name)
    if phase == 'diamond':
      self.portal = base + PORTAL_SUFFIX + family
    else:
      self.portal = name + PORTAL_SUFFIX
    self.table = None           # Portal table to write back.
    self.key_fields = []
    self.key_types = []
    self.has_value = True
    self.aggregation = None     # 'sum' | 'min' | 'max' | 'or'.
    self.neutral = None
    self.functional = False     # Defined with = : one value per key.
    self.contributions = []


class LoopGroup(object):
  """A recursion loop inside a learning cone.

  Its members are compiled from their diamond forms and iterated to
  stabilization; the forward probe determines the sweep count, and the
  gradient flows through a scan of that length."""

  def __init__(self, origins):
    self.origins = list(origins)
    self.members = []
    self.repetitions = 1000  # Sweep cap of the probe.
    self.sweeps = None       # Determined by the forward probe.


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
    self.written_tables = {}    # predicate -> table filled by WriteBack.
    self.constant_keys = collections.defaultdict(set)  # class -> keys.
    self.class_types = {}       # column class -> 'Str' | 'Num'.
    self.synthetic_count = 0    # For axes of computed head keys.
    self.allocator = rule_translate.NamesAllocator()
    for diamond_name in iteration['predicates']:
      if ParsePhase(diamond_name)[1] != 'diamond':
        Error('Neural iteration got a non-diamond predicate %s.' %
              color.Warn(diamond_name), self.name)
      self.members.append(self.CompileMember(diamond_name))
    self.ResolveClassTypes()

  def ResolveClassTypes(self):
    """Checks that every axis class received a type.

    Types spread through the shared classes by construction: any typed
    column of a class types the whole class, so no fixpoint is needed.
    """
    def Ensure(column_class, description, context):
      if self.ClassType(column_class) is None:
        Error('Could not infer whether %s holds strings or numbers; '
              'bind it through a typed relation.' % description, context)
    for member in self.members:
      for position, column_class in enumerate(member.key_types):
        Ensure(column_class,
               'key column %s of %s' % (
                   color.Warn(str(member.key_fields[position])),
                   color.Warn(member.name)), member.name)
      for contribution in member.contributions:
        for variable in contribution.axes:
          Ensure(contribution.axis_type.get(variable),
                 'a join variable of %s' % color.Warn(member.name),
                 contribution.rule_text)

  # ----------------------------- Compilation -----------------------------

  def PredicateSignature(self, predicate_name):
    signatures = self.program.predicate_signatures
    if predicate_name not in signatures:
      Error('Neural compilation needs type inference, but predicate '
            '%s has no signature.' % color.Warn(predicate_name),
            self.name)
    return signatures[predicate_name]

  def Signature(self, predicate_name, display_name=None):
    """([key fields], [column classes], has_value) of a predicate.

    Every key column belongs to a join-class of columns (its own tensor
    axis with its own numbering); the SQL-inferred type, when known,
    types the whole class."""
    display_name = display_name or predicate_name
    signature = self.PredicateSignature(predicate_name)
    key_fields = []
    key_classes = []
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
      if rendered not in ('Str', 'Num', 'Any'):
        Error('Neural keys must be strings or numbers; column %s of %s '
              'is %s.' %
              (color.Warn(str(field)), color.Warn(display_name),
               color.Warn(rendered)), display_name)
      column_class = self.program.column_classes.OfColumn(
          predicate_name, field)
      if rendered != 'Any':
        self.SetClassType(column_class, rendered, display_name)
      key_fields.append(field)
      key_classes.append(column_class)
    return key_fields, key_classes, has_value

  def SetClassType(self, column_class, class_type, context):
    known = self.class_types.get(column_class)
    if known is None:
      self.class_types[column_class] = class_type
    elif known != class_type:
      Error('A column class mixes strings and numbers near %s.' %
            color.Warn(str(context)), str(context))

  def ClassType(self, column_class):
    return self.class_types.get(column_class)

  def IsStateRelation(self, predicate_name):
    """State relations live in the plan's memory, not in stored tables."""
    return ParsePhase(predicate_name)[1] == 'portal'

  def RelationOf(self, predicate_name, context):
    """Relation spec of a leaf predicate: plan state or a stored input."""
    if predicate_name in self.relations:
      return self.relations[predicate_name]
    key_fields, key_types, has_value = self.Signature(predicate_name)
    relation = Relation(predicate_name, key_fields, key_types, has_value)
    self.relations[predicate_name] = relation
    if not self.IsStateRelation(predicate_name):
      ground = self.program.annotations.Ground(predicate_name)
      if ground is None:
        Error('Neural rules may only read recursive state and stored '
              'relations. Predicate %s is neither.' %
              color.Warn(predicate_name), context)
      self.input_tables[predicate_name] = ground.table_name
    return relation

  def CompileMember(self, diamond_name):
    """Member of a recursion loop, compiled from its diamond rules."""
    base, phase, family = ParsePhase(diamond_name)
    member_name = base + family
    member = Member(member_name, diamond_name)
    # Checking the signature first: it produces the clearest errors
    # (e.g. string-valued predicates are outside of the fragment).
    member.key_fields, member.key_types, member.has_value = self.Signature(
        diamond_name, member_name)
    ground = self.program.annotations.Ground(diamond_name)
    assert ground, 'Diamond predicates are always grounded.'
    member.table = ground.table_name
    rules = [r for name, r in self.program.rules if name == diamond_name]
    assert rules, 'Diamond predicate %s has no rules.' % diamond_name
    self.CompileContributions(member, rules)
    return member

  def CompileContributions(self, member, rules):
    """Contributions of a member from its rules.

    Rules aggregating with +=, Min= or Max= combine in the corresponding
    semiring; a functional (=) rule derives a single value per key, over
    which Max is exact. A rule that aggregates over the multi-body
    auxiliary predicate is expanded into the auxiliary's rules."""
    aggregations = set()
    functional_rules = 0
    pending = []  # (structure, aggregated expression).
    for rule in rules:
      rs = ExtractStructure(self.program, rule, self.allocator)
      if not member.has_value:
        aggregations.add('or')
        pending.append((rs, None))
        continue
      value = rs.select.get('logica_value')
      if (isinstance(value, dict) and 'call' in value and
          value['call']['predicate_name'] in AGGREGATIONS):
        aggregations.add(value['call']['predicate_name'])
        pending.append((rs, FieldValues(value['call'])[0]))
      else:
        aggregations.add('Max')
        functional_rules += 1
        pending.append((rs, value))
    if len(aggregations) != 1:
      Error('Rules of %s mix different aggregations.' %
            color.Warn(member.name), member.name)
    [aggregation] = aggregations
    if aggregation == 'or':
      member.aggregation, member.neutral = 'or', False
    else:
      member.aggregation, member.neutral = AGGREGATIONS[aggregation]
    # Defined purely with = : the runtime verifies one value per key.
    member.functional = (member.has_value and
                         functional_rules == len(rules))
    for rs, aggregated_expr in pending:
      aux_predicates = [p for p in rs.tables.values() if AUX_MARKER in p]
      if aux_predicates and len(rs.tables) == 1:
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
        field_class = relation.key_types[relation.key_fields.index(field)]
        if var in value_vars:
          Error('Neural fragment does not allow joining a key with a '
                'value; variable in rule of %s.' % color.Warn(member.name),
                contribution.rule_text)
        if axis_of.get(var) not in (None, field_class):
          Error('Variable joins keys of unrelated column classes in '
                'rule of %s.' % color.Warn(member.name),
                contribution.rule_text)
        axis_of[var] = field_class
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
      if var not in axis_of:
        # A variable bound only by the list gets its own axis class.
        self.synthetic_count += 1
        axis_of[var] = ('list-axis', self.name, self.synthetic_count)
      self.SetClassType(axis_of[var], element_type,
                        contribution.rule_text)
      self.constant_keys[axis_of[var]] |= set(values)
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

    # A key equated with a literal (e.g. Activation(e, 0, 10)) demands
    # that literal in the domain even if no input relation mentions it.
    for constraint in contribution.constraints:
      call = constraint.get('call')
      if not call or call['predicate_name'] != '==':
        continue
      sides = FieldValues(call)
      for variable_node, literal_node in (sides, reversed(sides)):
        if not IsVariable(variable_node):
          continue
        variable = canonical(VariableName(variable_node))
        literal = LiteralValue(literal_node)
        if variable in axis_of and literal is not None:
          self.SetClassType(axis_of[variable],
                            'Str' if isinstance(literal, str) else 'Num',
                            contribution.rule_text)
          self.constant_keys[axis_of[variable]].add(literal)

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
      if (self.IsStateRelation(name) or
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
    ConfigureJax(jax)
    import jax.numpy as jnp
    import numpy as np

    # 1-3. Input tables -> domains -> dense tensors.
    input_data = self.LoadInputs(sql_runner)
    domains, index, domain_arrays = self.BuildDomains(input_data, jnp)
    tensors = self.BuildTensors(input_data, domains, index, jnp, np)

    def Dims(relation):
      return tuple(len(domains[t]) for t in relation.key_types)

    # 4. State: portals start empty.
    state = {}
    for member in self.members:
      portal = member.portal
      relation = Relation(portal, member.key_fields, member.key_types,
                          member.has_value)
      self.relations.setdefault(portal, relation)
      shape = Dims(relation)
      values = (jnp.full(shape, member.neutral, dtype=jnp.float64)
                if member.has_value else None)
      state[portal] = (jnp.zeros(shape, dtype=bool), values)

    runtime = Runtime(self, jnp, domains, domain_arrays, index)
    member_functions = [(m, runtime.MemberFunction(m)) for m in self.members]

    # Tensors ride as a closure constant: lazily built entries are not
    # a pytree, and only the state changes between sweeps anyway.
    def Sweep(state):
      state = dict(state)
      for member, function in member_functions:
        state[member.portal] = function(state, tensors)
      return state

    sweep = jax.jit(Sweep)

    # 5. Iterate to stabilization.
    iterations = 0
    converged = False
    for iterations in range(1, self.repetitions + 1):
      new_state = sweep(state)
      if self.Converged(state, new_state, jnp):
        state = new_state
        converged = True
        break
      state = new_state
      if progress and iterations % 32 == 0:
        progress(iterations)

    self.CheckFunctionalConsistency(runtime, state, tensors, domains,
                                    jnp, np)

    # 6. Write the stabilized relations back into portal tables.
    for member in self.members:
      self.WriteBack(sql_runner, member,
                     state[member.portal], domains, np)

    return {'iterations': iterations, 'converged': converged}

  def FieldColumn(self, field):
    return 'col%d' % field if isinstance(field, int) else field

  def CheckFunctionalConsistency(self, runtime, state, tensors, domains,
                                 jnp, np):
    """Verifies that every =-defined member derives one value per key.

    A functional member is consistent iff aggregating its candidates
    with min gives the same relation as aggregating with max: one
    comparison catches conflicts both between rules and within a rule.
    """
    for member in self.members:
      if not member.functional:
        continue
      shadow = Member(member.name, member.diamond_name)
      shadow.key_fields = member.key_fields
      shadow.key_types = member.key_types
      shadow.has_value = True
      shadow.aggregation, shadow.neutral = 'min', float('inf')
      shadow.contributions = member.contributions
      max_mask, max_values = runtime.MemberFunction(member)(state, tensors)
      unused_mask, min_values = runtime.MemberFunction(shadow)(state,
                                                              tensors)
      conflict = np.asarray(max_mask & (max_values != min_values))
      if conflict.any():
        position = tuple(int(i) for i in np.argwhere(conflict)[0])
        keys = tuple(domains[c][i]
                     for c, i in zip(member.key_types, position))
        Error('Predicate %s is defined with = but is not a function: '
              'key %s derives both %s and %s.' %
              (color.Warn(member.name), keys,
               float(np.asarray(min_values)[position]),
               float(np.asarray(max_values)[position])), member.name)

  def LoadInputs(self, sql_runner):
    """Reads input tables. Terminal runners return (header, rows),
    notebook runners return a pandas DataFrame."""
    input_data = {}
    for name, table in self.input_tables.items():
      result = sql_runner('SELECT * FROM %s' % table, self.engine,
                          is_final=True)
      if isinstance(result, tuple):
        header, rows = result
        input_data[name] = (list(header), [list(r) for r in rows])
      else:
        input_data[name] = (list(result.columns), result.values.tolist())
    return input_data

  def AxisClasses(self):
    """Every column class that serves as a tensor axis of this plan."""
    classes = set()
    for relation in self.relations.values():
      classes.update(relation.key_types)
    for member in self.members:
      classes.update(member.key_types)
      for contribution in member.contributions:
        classes.update(contribution.axis_type.values())
    classes.update(self.constant_keys)
    return classes

  def BuildDomains(self, input_data, jnp):
    """Builds one domain per column class: each axis numbers its own
    values. Constant keys of the rules participate even when no input
    relation mentions them."""
    domain_values = {column_class: set(constants)
                     for column_class, constants
                     in self.constant_keys.items()}
    for column_class in self.AxisClasses():
      domain_values.setdefault(column_class, set())
    for name, (header, rows) in input_data.items():
      relation = self.relations[name]
      for row in rows:
        for field, column_class in zip(relation.key_fields,
                                       relation.key_types):
          value = row[header.index(self.FieldColumn(field))]
          domain_values[column_class].add(value)
    domains = {c: sorted(domain_values[c], key=lambda v: (str(type(v)), v))
               for c in domain_values}
    index = {c: {v: i for i, v in enumerate(domains[c])} for c in domains}
    domain_arrays = {
        c: (jnp.array([float(v) for v in domains[c]], dtype=jnp.float64)
            if self.ClassType(c) != 'Str' else None)
        for c in domains}
    return domains, index, domain_arrays

  def BuildTensors(self, input_data, domains, index, jnp, np):
    """Row forms of the input relations; their dense (mask, values)
    pairs are built lazily — a relation fully served by the row path
    never pays for its dense cube."""
    self.input_rows = {}
    for name, (header, rows) in input_data.items():
      relation = self.relations[name]
      if not relation.key_fields:
        continue
      position = []
      for field, column_class in zip(relation.key_fields,
                                     relation.key_types):
        column = [row[header.index(self.FieldColumn(field))]
                  for row in rows]
        mapping = index[column_class]
        domain = np.asarray(domains[column_class])
        if domain.dtype.kind in 'if':
          indices = np.searchsorted(domain, np.asarray(column))
        else:
          indices = np.fromiter((mapping[v] for v in column),
                                dtype=np.int64, count=len(column))
        position.append(indices)
      # A table is a set: deduplicate the rows. Dense assignment keeps
      # the last write of a duplicated key and np.unique keeps the
      # first: reverse to agree.
      keys = np.stack(position, axis=1)[::-1]
      keys, kept = np.unique(keys, axis=0, return_index=True)
      row_values = None
      if relation.has_value:
        value_column = header.index('logica_value')
        row_values = np.asarray([row[value_column] for row in rows],
                                dtype=np.float64)[::-1][kept]
      self.input_rows[name] = (
          tuple(keys[:, d] for d in range(keys.shape[1])), row_values)

    def DenseTensor(name):
      header, rows = input_data[name]
      relation = self.relations[name]
      dims = tuple(len(domains[t]) for t in relation.key_types)
      mask = np.zeros(dims, dtype=bool)
      values = np.zeros(dims, dtype=np.float64)
      if relation.key_fields:
        position, row_values = self.input_rows[name]
        mask[position] = True
        if row_values is not None:
          values[position] = row_values
      else:
        value_column = (header.index('logica_value')
                        if relation.has_value else None)
        for row in rows:
          mask[()] = True
          if value_column is not None:
            values[()] = float(row[value_column])
      return (jnp.array(mask), jnp.array(values))

    return LazyTensors(DenseTensor)

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

  BULK_ROWS = 100000  # Above this, tables travel through a CSV file.

  def WriteBack(self, sql_runner, member, state_tensor, domains, np):
    """Writes a member's stabilized relation into its portal table."""
    self.written_tables[member.name] = member.table
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

    if len(positions) > self.BULK_ROWS and self.engine == 'duckdb':
      self.BulkWriteBack(sql_runner, member, positions, values, domains,
                         columns, np)
      return

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
        # Scientific notation makes the engine infer DOUBLE; a long
        # plain decimal would be parsed as a DECIMAL and overflow its
        # scale.
        literals.append(repr(int(v)) if integral_value else '%.17e' % v)
      rows.append('(%s)' % ', '.join(literals))
    sql = ('CREATE OR REPLACE TABLE %s AS '
           'SELECT * FROM (VALUES %s) AS t(%s)' % (
               member.table, ', '.join(rows), ', '.join(columns)))
    sql_runner(sql, self.engine, is_final=False)

  def BulkWriteBack(self, sql_runner, member, positions, values, domains,
                    columns, np):
    """Writes a large relation through a CSV file: a VALUES literal of
    millions of rows would dwarf the data itself."""
    import csv
    import tempfile
    frame = []
    for axis, column_class in enumerate(member.key_types):
      domain = np.asarray(domains[column_class], dtype=object)
      frame.append(domain[positions[:, axis]])
    if member.has_value:
      frame.append(values[tuple(positions.T)])
    with tempfile.NamedTemporaryFile(
        'w', suffix='.csv', delete=False, newline='') as f:
      writer = csv.writer(f)
      writer.writerow(columns)
      writer.writerows(zip(*frame))
      temporary = f.name
    sql_runner("CREATE OR REPLACE TABLE %s AS "
               "SELECT * FROM read_csv_auto('%s', header=true)" %
               (member.table, temporary), self.engine, is_final=False)
    os.remove(temporary)

  def __repr__(self):
    return 'NeuralPlan(%s: %s)' % (
        self.name, [m.name for m in self.members])


class NeuralTargetPlan(NeuralPlan):
  """Gradient descent of a scalar target over learned predicates.

  Training is a genuine dependency cycle: the parameters depend on the
  objective (Weight <- Loss) while the objective depends on the
  parameters (Loss <- Prediction <- Weight). Exactly as with recursive
  predicates, the cycle collapses into a single iterated node: this
  plan. Concertina schedules the acyclic condensation — the plan's
  inputs are the in-edges of the collapsed cycle (data and W_init) and
  its output is the learned W — while the cycle itself spins inside,
  as gradient descent, until the target stabilizes.

  The learning cone — every predicate on a path from a learned predicate
  to the target — is tensorized by the same fragment translator as
  neural recursion and evaluated as a differentiable function of the
  learned tensors. The learned predicates' own rules act purely as
  initialization: ordinary SQL computes them into <predicate>_init
  tables, which the plan reads as the starting point; the learned
  relations are then written into the learned predicates' tables, so
  every reader sees the trained values.
  """

  def __init__(self, program, iteration_name, iteration, target):
    self.program = program
    self.name = iteration_name
    self.engine = program.annotations.Engine()
    self.target = target
    self.learned = list(iteration['predicates'])
    self.members = []           # Cone members in topological order.
    self.relations = {}
    self.input_tables = {}
    self.written_tables = {}    # predicate -> table filled by WriteBack.
    self.constant_keys = collections.defaultdict(set)
    self.class_types = {}
    self.synthetic_count = 0
    self.allocator = rule_translate.NamesAllocator()

    annotation = program.annotations.annotations.get(
        '@NeuralTarget', {}).get(self.target, {})
    self.learning_rate = float(annotation.get('learning_rate', 0.01))
    self.steps = int(annotation.get('steps', 10000))
    self.epsilon = float(annotation.get('epsilon', 1e-12))
    optimize = annotation.get('optimize')
    if isinstance(optimize, dict):
      optimize = optimize.get('predicate_name')
    if optimize not in (None, 'Min', 'Max'):
      Error('@NeuralTarget optimize must be Min or Max, got %s.' %
            color.Warn(str(optimize)), self.target)
    self.maximize = (optimize == 'Max')

    self.CompileCone()

  # ----------------------------- Compilation -----------------------------

  def CompileCone(self):
    """Assembles the plan from the pre-extracted cone components."""
    components = self.program.neural_components.get(self.target)
    assert components is not None, (
        'Cone components of %s were not extracted.' % self.target)

    # Names computable as plan state: single members and loop members.
    self.cone_state = set()
    for kind, content in components:
      if kind == 'single':
        self.cone_state.add(content)
      else:
        self.cone_state.update(content)

    # Learned predicates are parameter leaves; their current value is
    # read from the initialization tables.
    for predicate in self.learned:
      self.RelationOf(predicate, self.name)
      init_ground = self.program.annotations.Ground(predicate + '_init')
      assert init_ground, 'Learned predicates are initialized and grounded.'
      self.input_tables[predicate] = init_ground.table_name

    # Stages: ('member', m) is evaluated once, ('loop', g) iterates the
    # diamond members of a recursion loop to stabilization.
    self.stages = []
    for kind, content in components:
      if kind == 'single':
        member = self.CompileConeMember(content)
        self.members.append(member)
        self.stages.append(('member', member))
      else:
        group = LoopGroup(content)
        for origin in content:
          group.members.append(self.CompileMember(origin + DIAMOND_SUFFIX))
        self.members.extend(group.members)
        group.repetitions = self.LoopRepetitions(content)
        self.stages.append(('loop', group))

    if components[-1][0] != 'single':
      Error('The target %s of @NeuralTarget is recursive; recursive '
            'targets are not supported.' % color.Warn(self.target),
            self.target)
    target_member = self.stages[-1][1]
    if target_member.key_fields:
      Error('The target of @NeuralTarget must be a zero-argument '
            'predicate; %s has keys.' % color.Warn(self.target),
            self.target)
    if not target_member.has_value:
      Error('The target %s of @NeuralTarget carries no numeric value.' %
            color.Warn(self.target), self.target)
    self.ResolveClassTypes()

  def LoopRepetitions(self, origins):
    """Sweep cap of a loop: its @Recursive counts, or the default."""
    recursive = self.program.annotations.annotations.get('@Recursive', {})
    counts = [int(recursive[p]['1']) for p in origins
              if p in recursive and '1' in recursive[p]]
    counts = [1000000000 if c == -1 else c for c in counts]
    return max(counts) if counts else 1000

  def CompileConeMember(self, predicate):
    member = Member(predicate, predicate)
    member.key_fields, member.key_types, member.has_value = self.Signature(
        predicate)
    rules = [r for name, r in self.program.rules if name == predicate]
    self.CompileContributions(member, rules)
    return member

  def IsStateRelation(self, predicate_name):
    return (predicate_name in self.cone_state or
            ParsePhase(predicate_name)[1] == 'portal')

  # ------------------------------- Runtime -------------------------------

  def Run(self, sql_runner, progress=None):
    try:
      import jax
    except ImportError:
      raise NeuralCompileException(
          'Neural execution requires JAX. Please run: '
          'python3 -m pip install jax', self.name)
    ConfigureJax(jax)
    import jax.numpy as jnp
    import numpy as np

    input_data = self.LoadInputs(sql_runner)
    domains, index, domain_arrays = self.BuildDomains(input_data, jnp)
    tensors = self.BuildTensors(input_data, domains, index, jnp, np)

    parameters = {p: tensors[p][1] for p in self.learned}
    masks = {p: tensors[p][0] for p in self.learned}

    runtime = Runtime(self, jnp, domains, domain_arrays, index)
    stage_functions = []
    for kind, content in self.stages:
      if kind == 'member':
        stage_functions.append(
            ('member', content, runtime.MemberFunction(content)))
      else:
        stage_functions.append(
            ('loop', content,
             [(m, runtime.MemberFunction(m)) for m in content.members]))
    sign = -1.0 if self.maximize else 1.0

    def Overlay(parameters):
      return tensors.Overlay(
          {p: (masks[p], parameters[p]) for p in self.learned})

    def EmptyLoopState(group):
      state = {}
      for member in group.members:
        shape = tuple(len(domains[t]) for t in member.key_types)
        values = (jnp.full(shape, member.neutral, dtype=jnp.float64)
                  if member.has_value else None)
        state[member.portal] = (
            jnp.zeros(shape, dtype=bool), values)
      return state

    def LoopSweep(functions, loop_state, environment):
      state = dict(loop_state)
      for member, function in functions:
        state[member.portal] = function(state, environment)
      return state

    def PublishLoop(group, loop_state, state):
      # At the fixpoint a loop member equals its portal; downstream
      # members read it by its own name.
      for member in group.members:
        stabilized = loop_state[member.portal]
        state[member.name] = stabilized
        state[member.portal] = stabilized

    def Probe(parameters):
      """Concrete forward pass, finding the sweep count of every loop.

      Structural recursion (layers, time as a key) stabilizes after a
      parameter-independent number of sweeps, so the count found under
      the initial parameters is frozen for training, with a margin of
      two sweeps: at the fixpoint extra sweeps are the identity."""
      current = Overlay(parameters)
      state = {}
      for kind, content, functions in stage_functions:
        if kind == 'member':
          state[content.name] = functions(state, current)
          continue
        environment = current.Overlay(state)
        loop_state = EmptyLoopState(content)
        converged = False
        sweeps = 0
        for sweeps in range(1, content.repetitions + 1):
          new_loop_state = LoopSweep(functions, loop_state, environment)
          if self.Converged(loop_state, new_loop_state, jnp):
            loop_state = new_loop_state
            converged = True
            break
          loop_state = new_loop_state
        if not converged:
          Error('Recursion of %s does not stabilize within %d sweeps '
                'under the initial parameters; learning through dynamic '
                'equilibria is not supported yet.' %
                (color.Warn(', '.join(content.origins)),
                 content.repetitions), self.target)
        content.sweeps = sweeps + 2
        if content.sweeps > 100:
          print('Warning: differentiating through %d sweeps of %s; '
                'memory of the gradient grows linearly with the sweep '
                'count.' % (content.sweeps, ', '.join(content.origins)))
        PublishLoop(content, loop_state, state)
      return state

    probe_state = Probe(parameters)
    self.CheckFunctionalConsistency(runtime, probe_state,
                                    Overlay(parameters), domains, jnp, np)

    def Target(parameters):
      current = Overlay(parameters)
      state = {}
      for kind, content, functions in stage_functions:
        if kind == 'member':
          state[content.name] = functions(state, current)
          continue
        environment = current.Overlay(state)

        def OneSweep(carry, unused_x, functions=functions,
                     environment=environment):
          return LoopSweep(functions, carry, environment), None

        loop_state, _ = jax.lax.scan(OneSweep, EmptyLoopState(content),
                                     None, length=content.sweeps)
        PublishLoop(content, loop_state, state)
      target_mask, target_value = state[self.target]
      return sign * target_value

    value_and_gradient = jax.jit(jax.value_and_grad(Target))

    trace = os.getenv('LOGICA_NEURAL_TRACE')
    previous = None
    steps_done = 0
    converged = False
    for steps_done in range(1, self.steps + 1):
      value, gradient = value_and_gradient(parameters)
      parameters = {p: parameters[p] - self.learning_rate * gradient[p]
                    for p in self.learned}
      value = float(value)
      if trace and (steps_done & (steps_done - 1)) == 0:  # Powers of two.
        norms = ' '.join(
            '|grad %s|=%.3g' % (p, float(abs(gradient[p]).sum()))
            for p in self.learned)
        print('step %d: target %g %s' % (steps_done, float(value), norms))
      if not math.isfinite(value):
        Error('Training of %s diverged (the target is %s at step %d); '
              'lower the learning_rate.' %
              (color.Warn(self.target), value, steps_done), self.target)
      if previous is not None and abs(previous - value) <= self.epsilon:
        converged = True
        break
      previous = value
      if progress and steps_done % 64 == 0:
        progress(steps_done)

    # Write the learned relations into the learned predicates' tables.
    for predicate in self.learned:
      relation = self.relations[predicate]
      learned_member = Member(predicate, predicate)
      learned_member.key_fields = relation.key_fields
      learned_member.key_types = relation.key_types
      learned_member.has_value = True
      ground = self.program.annotations.Ground(predicate)
      assert ground, 'Learned predicates are grounded by the rewrite.'
      learned_member.table = ground.table_name
      self.WriteBack(sql_runner, learned_member,
                     (masks[predicate], parameters[predicate]),
                     domains, np)

    return {'iterations': steps_done, 'converged': converged}

  def __repr__(self):
    return 'NeuralTargetPlan(%s -> %s, learn: %s)' % (
        self.name, self.target, self.learned)


class LazyTensors(object):
  """Dense input tensors built on first read: a table fully served by
  the row path never pays for its dense form."""

  def __init__(self, build):
    self.build = build
    self.cache = {}

  def __getitem__(self, name):
    if name not in self.cache:
      import jax
      # The first read may happen inside a jit trace; the built tensor
      # is a constant and must stay concrete to be cached and reused
      # outside of the trace.
      with jax.ensure_compile_time_eval():
        self.cache[name] = self.build(name)
    return self.cache[name]

  def Overlay(self, overrides):
    """A view with some entries replaced, e.g. the learned parameters
    of the current step."""
    result = LazyTensors(self.__getitem__)
    result.cache = dict(overrides)
    return result


def NeedsDenseEvaluator(node, relations, row_variables, string_variables,
                        canonical):
  """True when an expression needs the dense axes. A combine opens a
  child axis context; a keyed relation read is a row-wise gather only
  when every key is a row-bound variable; a string key may serve as a
  gather key but cannot enter arithmetic or comparisons."""
  def Scan(node):
    if isinstance(node, dict):
      if 'combine' in node:
        return True
      call = node.get('call')
      if (call and call['predicate_name'] in relations and
          call['record']['field_value']):
        for field_value in call['record']['field_value']:
          expression = field_value['value']['expression']
          if (not IsVariable(expression) or
              canonical(VariableName(expression)) not in row_variables):
            return True
        return False  # A gather; its keys need no further scanning.
      if IsVariable(node):
        return canonical(VariableName(node)) in string_variables
      return any(Scan(v) for v in node.values())
    if isinstance(node, list):
      return any(Scan(v) for v in node)
    return False
  return Scan(node)


def ConfigureJax(jax):
  """Numeric precision and the persistent compilation cache.

  The programs are small, so XLA compilation (~hundreds of ms) dominates
  a CLI run; the on-disk cache brings repeat runs to the training cost
  itself. LOGICA_JAX_CACHE overrides the location, empty disables."""
  jax.config.update('jax_enable_x64', True)
  cache_dir = os.environ.get(
      'LOGICA_JAX_CACHE', os.path.expanduser('~/.cache/logica/jax'))
  if not cache_dir:
    return
  try:
    jax.config.update('jax_compilation_cache_dir', cache_dir)
    # Default thresholds only cache compilations over a second: exactly
    # backwards for a fleet of small graphs.
    jax.config.update('jax_persistent_cache_min_compile_time_secs', 0.0)
    jax.config.update('jax_persistent_cache_min_entry_size_bytes', 0)
  except Exception:
    pass  # An older JAX without the persistent cache: run without it.


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
        aligned_mask = context.Aligned(relation_mask, variables)
        mask = mask & aligned_mask
        if value_var is not None:
          # Masked-out cells hold the semiring neutral (e.g. -inf for
          # Max); reading them as 0 keeps infinities out of the
          # arithmetic — and out of the gradient (inf * 0 = nan in the
          # chain rule). The row is dropped by the mask anyway.
          context.environment[value_var] = jnp.where(
              aligned_mask, context.Aligned(relation_values, variables),
              0.0)

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

    return self.RowContributionFunction(member, contribution,
                                        Evaluate) or Evaluate

  def RowContributionFunction(self, member, contribution, dense_evaluate):
    """A single-read contribution rides the rows of its input table:
    O(rows) work and memory instead of a dense cube over the domains.
    Returns None when the contribution does not fit the pattern."""
    jnp = self.jnp
    keyed = [r for r in contribution.reads
             if self.plan.relations[r[0]].key_fields]
    scalars = [r for r in contribution.reads
               if not self.plan.relations[r[0]].key_fields]

    def KeyVariables(read):
      read_name, read_key_map, _ = read
      return [read_key_map[f]
              for f in self.plan.relations[read_name].key_fields]

    # The driver is an input-table read binding every axis: the rule's
    # derivations are exactly its rows. Other keyed reads join on the
    # driver's variables — gathers at the rows' key positions.
    drivers = [
        r for r in keyed
        if r[0] in getattr(self.plan, 'input_rows', {})
        and len(set(KeyVariables(r))) == len(KeyVariables(r))
        and set(KeyVariables(r)) == set(contribution.axes)]
    if not drivers:
      return None
    name, key_map, value_var = drivers[0]
    relation = self.plan.relations[name]
    key_variables = [key_map[f] for f in relation.key_fields]
    others = [r for r in keyed if r is not drivers[0]]
    if any(kind != 'var' for kind, _ in contribution.head):
      return None
    if member.has_value and member.aggregation not in ('sum', 'min', 'max'):
      return None
    string_variables = {v for v, t in zip(key_variables, relation.key_types)
                        if self.domain_arrays[t] is None}
    scanned = ([contribution.value_expr] if member.has_value else [])
    scanned += list(contribution.definitions.values())
    scanned += list(contribution.constraints)
    if NeedsDenseEvaluator(scanned, self.plan.relations,
                           set(key_variables), string_variables,
                           contribution.canonical.Find):
      return None

    def Evaluate(state, tensors):
      if name in state or name not in getattr(self.plan, 'input_rows', {}):
        return dense_evaluate(state, tensors)
      positions, row_values = self.plan.input_rows[name]
      n = positions[0].shape[0]
      position_of = dict(zip(key_variables, positions))
      context = EvalContext(self, member, contribution, [], {},
                            state, tensors, row_positions=position_of)
      for variable, column_class, p in zip(key_variables,
                                           relation.key_types, positions):
        if self.domain_arrays[column_class] is not None:
          context.environment[variable] = self.domain_arrays[column_class][p]
      if value_var is not None:
        context.environment[value_var] = row_values
      valid = jnp.ones(n, dtype=bool)
      for scalar_name, _, scalar_value_var in scalars:
        scalar_mask, scalar_values = context.Tensor(scalar_name)
        valid = valid & jnp.broadcast_to(scalar_mask, (n,))
        if scalar_value_var is not None:
          context.environment[scalar_value_var] = jnp.where(
              scalar_mask, scalar_values, 0.0)
      for other in others:
        other_name, _, other_value_var = other
        other_mask, other_values = context.Tensor(other_name)
        position = tuple(position_of[v] for v in KeyVariables(other))
        other_mask = other_mask[position]
        valid = valid & other_mask
        if other_value_var is not None:
          context.environment[other_value_var] = jnp.where(
              other_mask, other_values[position], 0.0)
      for variable, values in contribution.memberships:
        allowed = set(values)
        domain = self.domains[contribution.axis_type[variable]]
        vector = jnp.array([v in allowed for v in domain], dtype=bool)
        valid = valid & vector[position_of[variable]]
      for constraint in contribution.constraints:
        valid = valid & jnp.broadcast_to(
            context.EvalConstraint(constraint), (n,))
      value = None
      if member.has_value:
        value, value_valid = context.Eval(contribution.value_expr)
        value = jnp.broadcast_to(value, (n,))
        if value_valid is not True:
          valid = valid & jnp.broadcast_to(value_valid, (n,))

      # Scatter the rows onto the member's key cells.
      sizes = [len(self.domains[t]) for t in member.key_types]
      total = 1
      flat = jnp.zeros(n, dtype=jnp.int64)
      for (_, variable), size in zip(contribution.head, sizes):
        flat = flat * size + position_of[variable]
        total *= size
      mask = jnp.zeros(total, dtype=bool).at[flat].max(valid)
      if value is not None:
        # Invalid rows carry the neutral: identity for their cell.
        contributed = jnp.where(valid, value, member.neutral)
        out = jnp.full(total, member.neutral, dtype=jnp.float64)
        if member.aggregation == 'sum':
          out = out.at[flat].add(contributed)
        elif member.aggregation == 'min':
          out = out.at[flat].min(contributed)
        else:
          out = out.at[flat].max(contributed)
        value = out.reshape(sizes)
      return mask.reshape(sizes), value

    return Evaluate


class EvalContext(object):
  """Evaluation of expression ASTs over a set of axes.

  Eval returns a pair (value, valid): valid is True or a boolean array;
  a row with an invalid value produces no derivation, mirroring the NULL
  produced in SQL by e.g. an inner aggregation over the empty set.
  """

  def __init__(self, runtime, member, contribution, axes, axis_type,
               state, tensors, parent=None, row_positions=None):
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
    # In a row context variables are bound to rows of a table rather
    # than to axes: keyed relation reads gather at these positions.
    self.row_positions = row_positions or {}

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
    if variables and all(v in self.row_positions for v in variables):
      # A row context: gather the read at the rows' key positions.
      position = tuple(self.row_positions[v] for v in variables)
      row_mask = mask[position]
      return (self.jnp.where(row_mask, values[position], 0.0), row_mask)
    aligned_values = self.Aligned(values, variables) if variables else values
    aligned_mask = self.Aligned(mask, variables) if variables else mask
    # Masked-out cells hold the semiring neutral; reading them as 0
    # keeps infinities out of the arithmetic and out of the gradient.
    return self.jnp.where(aligned_mask, aligned_values, 0.0), aligned_mask

  def TryEinsumContraction(self, inner):
    """Sum{R1(...) * R2(...)} as an einsum, when the pattern fits.

    A sum over a product of relation reads is a contraction: einsum
    computes it without materializing the cube of all variables — the
    memory stays linear in the inputs and the output. Rows absent from a
    relation read as 0, which for summation is exactly absence; validity
    of an output cell is the positive count of contributing row pairs.
    Returns None when the expression is not such a contraction."""
    jnp = self.jnp
    call = inner.get('call') if isinstance(inner, dict) else None
    if not call or call['predicate_name'] != '*':
      return None
    reads = []
    for factor in FieldValues(call):
      factor_call = factor.get('call') if isinstance(factor, dict) else None
      if (not factor_call or
          factor_call['predicate_name'] not in self.runtime.plan.relations):
        return None
      relation = self.runtime.plan.relations[factor_call['predicate_name']]
      if not relation.has_value:
        return None
      variables = []
      for field_value in factor_call['record']['field_value']:
        expression = field_value['value']['expression']
        if not IsVariable(expression):
          return None
        variables.append(self.Canonical(VariableName(expression)))
      if len(set(variables)) != len(variables):
        return None  # A diagonal read; the general path handles it.
      reads.append((relation, variables))

    letters = {}
    def LetterOf(variable):
      if variable not in letters:
        letters[variable] = chr(ord('a') + len(letters))
      return letters[variable]
    operand_specs = [''.join(LetterOf(v) for v in variables)
                     for _, variables in reads]
    for variable in letters:
      if (variable not in self.axis_position and
          self.KnowsVariable(variable)):
        return None  # Bound by a definition: the general path handles it.
    output_variables = [v for v in letters if v in self.axis_position]
    specification = '%s->%s' % (
        ','.join(operand_specs),
        ''.join(LetterOf(v) for v in output_variables))

    operands = []
    counting_operands = []
    for relation, variables in reads:
      mask, values = self.Tensor(relation.name)
      operands.append(jnp.where(mask, values, 0.0))
      counting_operands.append(mask.astype(jnp.float64))
    value = jnp.einsum(specification, *operands)
    counts = jnp.einsum(specification, *counting_operands)
    return (self.Aligned(value, output_variables),
            self.Aligned(counts > 0.0, output_variables))

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

    if op == 'Sum':
      contraction = self.TryEinsumContraction(inner)
      if contraction is not None:
        return contraction

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
        reduced = reduction(masked, local_dims)
        has_rows = jnp.any(valid, axis=local_dims)
      else:
        reduced, has_rows = masked, valid
      # An empty group is invalid; its value is read as 0, never as the
      # +-inf neutral, keeping infinities out of the gradient.
      return jnp.where(has_rows, reduced, 0.0), has_rows

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
        if (v in self.axis_position and
            self.runtime.plan.ClassType(self.axis_type[v]) == 'Str'):
          return v
      return None

    operations = {
        '==': lambda a, b: a == b, '!=': lambda a, b: a != b,
        '<': lambda a, b: a < b, '<=': lambda a, b: a <= b,
        '>': lambda a, b: a > b, '>=': lambda a, b: a >= b}

    left_axis, right_axis = StringAxis(left_node), StringAxis(right_node)
    if left_axis or right_axis:
      # A class domain is sorted, so index order coincides with the
      # lexicographic order of the strings: comparisons act on indices
      # (axis vs axis of the same class) or on a precomputed boolean
      # vector (axis vs literal).
      if left_axis and right_axis:
        if self.axis_type[left_axis] != self.axis_type[right_axis]:
          Error('String keys of unrelated column classes cannot be '
                'compared.', self.contribution.rule_text)
        size = len(self.runtime.domains[self.axis_type[left_axis]])
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
           for value in self.runtime.domains[self.axis_type[axis]]],
          dtype=bool)
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


