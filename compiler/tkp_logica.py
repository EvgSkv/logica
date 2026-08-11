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

"""TKP (top-k proofs): marking the world of probabilistic DNFs.

Works on the logical program after functor expansion, before any SQL.
The protocol is anchor names: TkpMakeFact, TkpProbConjunction, TkpTop,
TkpProbability. Everything else is wrappers: the detector knows nothing
about the shipped MakeFact and resolves any call through definitions
down to the anchors. A wrapper must resolve unambiguously: one
functional rule whose body is an expression; branching wrappers are a
loud error.

The result is a TkpWorld: which predicates are proof-valued, their k,
their atoms (the link to the probability predicate is syntactic:
probability: must be a direct call), conjunction contributions and the
probability read sites.
"""

import copy

if '.' not in __package__:
  from common import color
else:
  from ..common import color

###############################################################################
# I. The name protocol.
#
# Anchors are the only fixed names; everything else resolves to them
# through definitions. Machinery suffixes (_diamond, _portal, _fN) are
# folded by the normalize callback of the plan; TkpProb_P is the Num
# relation publishing the probability of the proof-valued P.

ANCHORS = {'TkpMakeFact', 'TkpProbConjunction', 'TkpTop',
           'TkpProbability'}


def AnchorOf(name):
  """Canonical anchor of a name; imports namespace (Tkp_TkpMakeFact)."""
  if name in ANCHORS:
    return name
  for anchor in ANCHORS:
    if name.endswith('_' + anchor):
      return anchor
  return None


def ProbabilityRelationName(predicate):
  return 'TkpProb_' + predicate


RESOLUTION_DEPTH = 24


###############################################################################
# II. AST analysis and resolution.


class TkpCompileException(Exception):

  def __init__(self, message, context):
    super().__init__(message)
    self.context = context

  def ShowMessage(self):
    print(color.Format('[ {error}Error{end} ] {msg} (%s)' % self.context,
                       {'msg': str(self)}))


def Error(message, context):
  raise TkpCompileException(message, context)


def CallName(expression):
  if isinstance(expression, dict) and 'call' in expression:
    return expression['call']['predicate_name']
  return None


def CallFields(call):
  """{field name or position: expression}."""
  result = {}
  for fv in call['record']['field_value']:
    result[fv['field']] = fv['value']['expression']
  return result


def FunctionalDefinitions(rules):
  """name -> rules of the form F(...) = expression."""
  result = {}
  for name, rule in rules:
    head_fields = rule['head']['record']['field_value']
    value_fields = [fv for fv in head_fields
                    if fv['field'] == 'logica_value']
    if len(value_fields) != 1:
      continue
    if 'expression' not in value_fields[0]['value']:
      continue  # An aggregation is not a functional definition.
    result.setdefault(name, []).append(rule)
  return result


def Substitute(expression, environment):
  """A copy of the expression with environment variables substituted."""
  if isinstance(expression, dict):
    if ('variable' in expression and
        expression['variable'].get('var_name') in environment):
      return copy.deepcopy(environment[expression['variable']['var_name']])
    return {key: Substitute(value, environment)
            for key, value in expression.items()}
  if isinstance(expression, list):
    return [Substitute(value, environment) for value in expression]
  return expression


def ResolveToAnchor(expression, definitions, context, depth=0):
  """Resolves an expression through definitions down to an anchor.

  Returns (anchor name, call node with substituted arguments), or
  (None, expression) when the chain ends elsewhere."""
  if depth > RESOLUTION_DEPTH:
    Error('TKP resolution is too deep; a definition cycle?', context)
  name = CallName(expression)
  if name is None:
    return None, expression
  anchor = AnchorOf(name)
  if anchor is not None:
    return anchor, expression
  candidates = definitions.get(name, [])
  if len(candidates) != 1:
    return None, expression  # Ambiguous wrapper: not our world.
  rule = candidates[0]
  head_fields = rule['head']['record']['field_value']
  parameters = []
  body_expression = None
  for fv in head_fields:
    if fv['field'] == 'logica_value':
      body_expression = fv['value']['expression']
    else:
      parameter = fv['value']['expression']
      if not (isinstance(parameter, dict) and 'variable' in parameter):
        return None, expression  # A tricky definition, not a wrapper.
      parameters.append((fv['field'], parameter['variable']['var_name']))
  if rule.get('body') is not None:
    return None, expression  # A wrapper with a body is not transparent.
  actual_fields = CallFields(expression['call'])
  environment = {}
  for field, variable in parameters:
    if field not in actual_fields:
      return None, expression
    environment[variable] = actual_fields[field]
  return ResolveToAnchor(Substitute(body_expression, environment),
                         definitions, context, depth + 1)


def LiteralValue(expression):
  literal = expression.get('literal') if isinstance(expression, dict) else None
  if literal is None:
    return None
  if 'the_string' in literal:
    return literal['the_string']['the_string']
  if 'the_number' in literal:
    return literal['the_number']['number']
  return None


def VariableName(expression):
  if isinstance(expression, dict) and 'variable' in expression:
    return expression['variable']['var_name']
  return None


###############################################################################
# III. The world marking.


class TkpAtom(object):
  """An atomic TKP predicate: Edge = MakeFact(...)."""

  def __init__(self, name, label, key_variables, probability_predicate,
               probability_keys, rule):
    self.name = name
    self.body_relation = None   # EDB body relation enumerating the facts
    self.label = label                # predicate: "Edge"
    self.key_variables = key_variables        # args: [a, b]
    self.probability_predicate = probability_predicate  # EdgeProb
    self.probability_keys = probability_keys  # variables of the call
    self.rule = rule


class TkpWorld(object):
  """The marking of the TKP world of a program."""

  def __init__(self, normalize=None):
    self.normalize = normalize or (lambda name: name)
    self.predicates = {}     # name -> k of a proof-valued predicate
    self.atoms = {}          # name -> TkpAtom
    self.probability_predicates = set()
    self.disjunction_rules = []   # (name, rule, expr, reads, guards)
    self.probability_reads = []   # (owner rule, TkpProbability call)

  def IsTkp(self, name):
    canonical = self.normalize(name)
    return canonical in self.predicates or canonical in self.atoms


def AggregationOperator(rule):
  """The aggregation operator of the head value, if any."""
  for fv in rule['head']['record']['field_value']:
    if fv['field'] == 'logica_value' and 'aggregation' in fv['value']:
      expression = fv['value']['aggregation']['expression']
      return CallName(expression), expression
  return None, None


def DisjunctionK(operator, definitions, context):
  """Resolves an aggregation operator to TkpTop(MergeList(x), k) -> k."""
  synthetic = {'call': {'predicate_name': operator, 'record':
               {'field_value': [{'field': 0, 'value': {'expression':
                {'variable': {'var_name': 'tkp_probe_'}}}}]}}}
  anchor, resolved = ResolveToAnchor(synthetic, definitions, context)
  if anchor != 'TkpTop':
    return None
  fields = CallFields(resolved['call'])
  k = LiteralValue(fields.get(1, {}))
  if k is None:
    Error('TKP: k of %s must resolve to a literal.' %
          color.Warn(operator), context)
  inner = fields.get(0)
  inner_name = CallName(inner) or ''
  if not inner_name.endswith('MergeList'):
    Error('TKP: aggregation %s must resolve to '
          'TkpTop(MergeList(x), k).' % color.Warn(operator), context)
  if int(k) <= 0:
    # The SQL side reads k < 0 as "no truncation"; tensor state is
    # statically shaped by k slots, so unlimited proofs have no
    # tensor representation. Refuse loudly rather than slice wrongly.
    Error('TKP neural: k of %s must be a positive literal; '
          'k < 0 (no truncation) exists only on the SQL side.' %
          color.Warn(operator), context)
  return int(k)


def ParseAtom(name, resolved_call, rule, context):
  """TkpMakeFact(predicate:, args:, probability:) -> TkpAtom."""
  fields = CallFields(resolved_call['call'])
  label = LiteralValue(fields.get('predicate', {}))
  if not isinstance(label, str):
    Error('TKP: predicate: of a fact must be a string literal.', context)
  args_expression = fields.get('args', {})
  the_list = (args_expression.get('literal', {})
              .get('the_list', {}).get('element'))
  if the_list is None:
    Error('TKP: args: of a fact must be a list of variables.', context)
  key_variables = [VariableName(e) for e in the_list]
  if None in key_variables:
    Error('TKP: args: of a fact must be a list of variables.', context)
  probability = fields.get('probability', {})
  probability_name = CallName(probability)
  if probability_name is None:
    Error('TKP: probability: of a fact must be a direct call of the '
          'probability predicate.', context)
  probability_fields = CallFields(probability['call'])
  probability_keys = [VariableName(probability_fields[position])
                      for position in sorted(probability_fields)]
  if probability_keys != key_variables:
    Error('TKP: args: %s must be exactly the keys of %s.' % (
        key_variables, color.Warn(probability_name)), context)
  return TkpAtom(name, label, key_variables, probability_name,
                 probability_keys, rule)


def TkpReadsOf(expression, world, definitions, context, reads):
  """Collects proof-valued reads and conjunctions of an expression."""
  name = CallName(expression)
  if name is not None:
    if world.IsTkp(name):
      reads.append(('read', expression))
      return
    anchor, resolved = ResolveToAnchor(expression, definitions, context)
    if anchor == 'TkpProbConjunction':
      fields = CallFields(resolved['call'])
      for position in sorted(fields):
        TkpReadsOf(fields[position], world, definitions, context, reads)
      reads.append(('conjunction', resolved))
      return
    if anchor == 'TkpMakeFact':
      reads.append(('atom', resolved))
      return
  if isinstance(expression, dict):
    for value in expression.values():
      TkpReadsOf(value, world, definitions, context, reads)
  elif isinstance(expression, list):
    for value in expression:
      TkpReadsOf(value, world, definitions, context, reads)


def ExtractTkpWorld(rules, normalize=None):
  """Builds the TKP world marking from the rules of the program.

  rules is a list of (name, rule) pairs as in program.rules; normalize
  folds the machinery names of unfolding (X_diamond, X_portal, X_f2)
  into the logical X — the suffix doctrine."""
  world = TkpWorld(normalize)
  definitions = FunctionalDefinitions(rules)

  # 1. Atoms: the value resolves into TkpMakeFact.
  for name, rule in rules:
    for fv in rule['head']['record']['field_value']:
      if fv['field'] != 'logica_value' or 'expression' not in fv['value']:
        continue
      anchor, resolved = ResolveToAnchor(
          fv['value']['expression'], definitions, name)
      if anchor == 'TkpMakeFact':
        fields = CallFields(resolved['call'])
        if all(VariableName(fields.get(f, {})) is not None
               for f in ('predicate', 'args', 'probability')):
          continue  # A pure pass-through: a wrapper, not an atom.
        if name in world.atoms:
          Error('TKP: atom %s must have a single rule.' %
                color.Warn(name), name)
        atom = ParseAtom(name, resolved, rule, name)
        conjuncts = (rule.get('body') or {}).get(
            'conjunction', {}).get('conjunct', [])
        for conjunct in conjuncts:
          body_predicate = conjunct.get('predicate', {})
          body_name = body_predicate.get('predicate_name')
          if body_name and body_name[:1].isalpha():
            if atom.body_relation is not None:
              Error('TKP: the fact rule of %s reads %s besides %s; the '
                    'runtime materializes ALL rows of the single body '
                    'relation as facts, so extra conjuncts would be '
                    'silently ignored. Filter in a separate predicate '
                    'and enumerate the facts from it.' % (
                        color.Warn(name), color.Warn(body_name),
                        color.Warn(atom.body_relation)), name)
            atom.body_relation = body_name
            continue
          unification = conjunct.get('unification')
          if (unification is not None and VariableName(
              unification['left_hand_side']) == 'logica_value'):
            continue
          Error('TKP: the fact rule of %s has a guard or computation '
                'in its body; the runtime materializes ALL rows of the '
                'body relation as facts and would silently ignore it. '
                'Filter in a separate predicate and enumerate the '
                'facts from it.' % color.Warn(name), name)
        if atom.body_relation is None:
          Error('TKP: the fact rule of %s must have a relational body '
                'enumerating the facts.' % color.Warn(name), name)
        world.atoms[name] = atom
        world.probability_predicates.add(atom.probability_predicate)

  # 2. Disjunctions: a head aggregation resolving into TkpTop.
  rules_by_name = {}
  for name, rule in rules:
    rules_by_name.setdefault(name, []).append(rule)

  def Contributions(name, rule):
    """Contributions of a disjunction: (rule, value expression).

    Multi-body aggregation hides contributions in _MultBodyAggAux
    rules; a single rule carries its contribution in the
    logica_value == expr unification."""
    conjuncts = (rule.get('body') or {}).get(
        'conjunction', {}).get('conjunct', [])
    for conjunct in conjuncts:
      aux = conjunct.get('predicate', {}).get('predicate_name', '')
      if '_MultBodyAggAux' in aux:
        result = []
        for aux_rule in rules_by_name.get(aux, []):
          for fv in aux_rule['head']['record']['field_value']:
            if fv['field'] == 'logica_value':
              value = fv['value']
              expression = value.get('expression')
              if expression is None and 'aggregation' in value:
                expression = value['aggregation']['expression']
              result.append((aux_rule, expression))
        return result
    # A single rule: the value is in a body unification (the unfolded
    # recursive form) or right in the head aggregation (the standalone
    # non-recursive form).
    for conjunct in conjuncts:
      unification = conjunct.get('unification')
      if unification is None:
        continue
      left = unification['left_hand_side']
      if VariableName(left) == 'logica_value':
        return [(rule, unification['right_hand_side'])]
    for fv in rule['head']['record']['field_value']:
      if fv['field'] == 'logica_value' and 'aggregation' in fv['value']:
        # The head keeps the OPERATOR call: T2P(contribution).
        operator_call = fv['value']['aggregation']['expression']
        argument = CallFields(operator_call['call']).get(0)
        return [(rule, argument)]
    return [(rule, None)]

  def ContributionGuards(contribution_rule, read_names, name):
    """Collects the RELATIONAL GUARDS of a contribution body.

    The first slice of the constraints layer: a body conjunct that is
    a plain relation over contribution variables filters the keys of
    the contribution — `Reach(a, c) TKP= Step(a, s, c) :-
    StartCell(a, s)` seeds reachability from the start only. The
    guard relation must be materialized and structural (independent
    of the learned parameters: the jax seam captures its rows at
    probe time). Everything else in a body stays a loud error:
    comparisons, computations and unifications would need value-level
    masks — the rest of the constraints design — and silently
    dropping them would change the meaning of the program."""
    guards = []
    conjuncts = (contribution_rule.get('body') or {}).get(
        'conjunction', {}).get('conjunct', [])
    for conjunct in conjuncts:
      predicate = conjunct.get('predicate', {}).get('predicate_name')
      if predicate is not None and predicate[:1].isalpha():
        if '_MultBodyAggAux' in predicate:
          continue
        if world.normalize(predicate) in read_names:
          continue
        if world.IsTkp(predicate):
          Error('TKP: contribution of %s reads the proof-valued %s '
                'in its body; proof reads belong in the value '
                'expression.' % (color.Warn(name),
                                 color.Warn(predicate)), name)
        fields = CallFields(conjunct['predicate'])
        variables = []
        for field in sorted(fields, key=FieldOrder):
          variable = VariableName(fields[field])
          if variable is None:
            Error('TKP: the guard %s of %s must hold plain '
                  'variables.' % (color.Warn(predicate),
                                  color.Warn(name)), name)
          variables.append(variable)
        guards.append((predicate, variables))
        continue
      unification = conjunct.get('unification')
      if (unification is not None and VariableName(
          unification['left_hand_side']) == 'logica_value'):
        continue
      Error('TKP: contribution of %s has a comparison or computation '
            'in its body; only relational guards over contribution '
            'variables are supported. Move the rest into a separate '
            'predicate feeding the proof reads.' % color.Warn(name),
            name)
    return guards

  for name, rule in rules:
    operator, argument = AggregationOperator(rule)
    if operator is None:
      continue
    k = DisjunctionK(operator, definitions, name)
    if k is None:
      continue
    canonical = world.normalize(name)
    known = world.predicates.get(canonical)
    if known is not None and known != k:
      Error('TKP: %s aggregates with two different k.' %
            color.Warn(canonical), name)
    world.predicates[canonical] = k
    contributions = Contributions(name, rule)
    if contributions and contributions[0][0] is not rule:
      # Multi-body form: contributions live in aux rules; the outer
      # rule itself must carry nothing beyond the machinery.
      ContributionGuards(rule, set(), name)
    for contribution_rule, expression in contributions:
      reads = []
      read_names = set()
      if expression is not None:
        TkpReadsOf(expression, world, definitions, name, reads)
        for kind, read in reads:
          if kind == 'read':
            read_names.add(world.normalize(CallName(read)))
      guards = ContributionGuards(contribution_rule, read_names,
                                  name)
      if expression is None:
        Error('TKP: cannot find the contribution of %s.' %
              color.Warn(name), name)
      known = set(ContributionHeadVariables(contribution_rule, name))
      for kind, read in reads:
        if kind == 'read':
          known.update(CallVariables(read, name))
      for guard_name, guard_vars in guards:
        for variable in guard_vars:
          if variable not in known:
            Error('TKP: the guard %s of %s binds %s, which is not a '
                  'contribution variable; a guard only filters '
                  'existing keys.' % (
                      color.Warn(guard_name), color.Warn(name),
                      color.Warn(variable)), name)
      world.disjunction_rules.append(
          (name, contribution_rule, expression, reads, guards))

  # 3. Probability reads: TkpProbability(...) in any expression.
  def FindProbabilityReads(node, owner):
    if isinstance(node, dict):
      if CallName(node) is not None:
        anchor, resolved = ResolveToAnchor(node, definitions, owner)
        if anchor == 'TkpProbability':
          world.probability_reads.append((owner, resolved))
          # Still look inside: the argument contains a TKP read.
      for value in node.values():
        FindProbabilityReads(value, owner)
    elif isinstance(node, list):
      for value in node:
        FindProbabilityReads(value, owner)

  for name, rule in rules:
    if name in world.predicates or name in world.atoms:
      continue
    FindProbabilityReads(rule, name)

  return world


###############################################################################
# IV. Rewriting probability reads: TkpProbability(P(keys)) -> TkpProb_P.


def RewriteProbabilityReads(rule, world, definitions):
  """A copy of the rule with probability reads as relation reads.

  A resolved TkpProbability(P(...)) becomes a call of TkpProb_P(...):
  an ordinary keyed state read for the numeric machinery."""
  def Walk(node):
    if isinstance(node, dict):
      name = CallName(node)
      if name is not None:
        anchor, resolved = ResolveToAnchor(node, definitions, name)
        if anchor == 'TkpProbability':
          fields = CallFields(resolved['call'])
          argument = fields.get(0) or fields.get('v')
          inner = CallName(argument)
          if inner is not None and world.IsTkp(inner):
            new_call = copy.deepcopy(argument)
            new_call['call']['predicate_name'] = (
                ProbabilityRelationName(inner))
            return new_call
      return {key: Walk(value) for key, value in node.items()}
    if isinstance(node, list):
      return [Walk(value) for value in node]
    return node
  return Walk(copy.deepcopy(rule))



###############################################################################
# V. The sparse proof algebra.
#
# A proof is a sorted tuple of fact ids; a value is a list of proofs in
# canonical order — the reference semantics of tkp.py carried onto the
# fact axis: ranking by probability with lexicographic ties (python
# tuple comparison IS the identity order, prefix first), absorption by
# kept proofs, truncation to k. Everything is python symbols: no
# tensors, no capacity, no virtual facts. Selection is data — the
# probability polynomial of the selected proofs is differentiated by
# the EXPLICIT product-rule formula (the custom gradient of the TKP
# node), so the fixpoint runs outside any autodiff tape and costs
# exactly its symbols.


def SparseProofProbability(proof, theta):
  """Product of the fact probabilities, in ascending fact order."""
  result = 1.0
  for fact in proof:
    result = result * theta[fact]
  return result


def SparseCanonicalize(pool, theta, k):
  """Dedup, absorption, order (probability desc, lex), top-k.

  k < 0 means no truncation (conjunction pools)."""
  ordered = sorted(set(pool))
  ordered.sort(key=lambda proof: -SparseProofProbability(proof, theta))
  result = []
  kept_sets = []
  for candidate in ordered:
    candidate_set = set(candidate)
    if any(kept <= candidate_set for kept in kept_sets):
      continue  # a duplicate, or absorbed by a likelier kept proof
    result.append(candidate)
    kept_sets.append(candidate_set)
    if k >= 0 and len(result) == k:
      break
  return result


def SparseConjunction(a, b, theta):
  """TkpProbConjunction: all pair unions, canonical, no truncation."""
  pool = []
  for proof_a in a:
    union_base = set(proof_a)
    for proof_b in b:
      pool.append(tuple(sorted(union_base.union(proof_b))))
  return SparseCanonicalize(pool, theta, -1)


def SparseProbability(proofs, theta):
  """Exact inclusion-exclusion over the stored proofs."""
  total = 0.0
  n = len(proofs)
  for chosen in range(1, 1 << n):
    union = set()
    size = 0
    for i in range(n):
      if chosen >> i & 1:
        union.update(proofs[i])
        size += 1
    sign = 1.0 if size % 2 == 1 else -1.0
    total += sign * SparseProofProbability(sorted(union), theta)
  return total


def SparseProbabilityGradient(proofs, theta, cotangent, out):
  """Adds cotangent * dP/dtheta into the list `out`, by product rule.

  Every inclusion-exclusion term is sign * prod(theta over its union);
  its derivative by theta_f is sign * product-without-f, computed via
  prefix/suffix products — never by division (theta may be 0)."""
  n = len(proofs)
  for chosen in range(1, 1 << n):
    union = set()
    size = 0
    for i in range(n):
      if chosen >> i & 1:
        union.update(proofs[i])
        size += 1
    facts = sorted(union)
    sign = 1.0 if size % 2 == 1 else -1.0
    prefix = 1.0
    prefixes = []
    for fact in facts:
      prefixes.append(prefix)
      prefix = prefix * theta[fact]
    suffix = 1.0
    for i in range(len(facts) - 1, -1, -1):
      out[facts[i]] += cotangent * sign * prefixes[i] * suffix
      suffix = suffix * theta[facts[i]]



class TkpMemberBase(object):
  """Common harness of a TKP member for the state machinery contract."""

  def __init__(self, name):
    self.name = name
    self.portal = name + '_tkp_portal'
    self.diamond_name = name + '_tkp_diamond'
    self.key_fields = []
    self.key_types = []
    self.has_value = True
    self.aggregation = 'tkp'
    self.neutral = 0.0
    self.contributions = []
    self.functional = False
    self.is_tkp = True


class TkpAtomMember(TkpMemberBase):
  """An atom: base one-fact proofs from the probability rows."""

  def __init__(self, atom):
    super().__init__(atom.name)
    self.atom = atom
    self.slots = 1


class TkpDisjunctionMember(TkpMemberBase):
  """A disjunction truncated to k; contributions: reads, conjunctions."""

  def __init__(self, name, k, contributions):
    super().__init__(name)
    self.k = k
    self.slots = k
    self.tkp_contributions = contributions  # (vars, tree, guards, rule)


class TkpProbabilityMember(TkpMemberBase):
  """Publishes the probability of a TKP predicate as a Num relation."""

  def __init__(self, of_member):
    super().__init__(ProbabilityRelationName(of_member.name))
    self.of_member = of_member
    self.key_fields = list(of_member.key_fields)
    self.key_types = list(of_member.key_types)


def FieldOrder(field):
  """THE canonical field order: positional numerically, then named
  alphabetically. Signatures, calls and heads must all sort with this
  one key, or the axes of a member and of its contributions transpose
  silently (a str key would also put positional field 10 before 2)."""
  return (isinstance(field, str), field)


def CallVariables(expression, context):
  """Variables of a proof-valued call, in canonical field order."""
  fields = CallFields(expression['call'])
  result = []
  for position in sorted(fields, key=FieldOrder):
    variable = VariableName(fields[position])
    if variable is None:
      Error('TKP: keys of a proof-valued read must be variables.',
            context)
    result.append(variable)
  if len(set(result)) != len(result):
    Error('TKP: repeated variable in a proof-valued read %s; diagonal '
          'unification is not implemented — the axes would misalign '
          'silently. Read with distinct variables and equate them in '
          'a separate predicate.' % color.Warn(str(result)), context)
  return result


def BuildContributionTree(expression, world, definitions, context):
  """Contribution tree: ('read', name, [vars]) | ('conj', l, r)."""
  name = CallName(expression)
  if name is None:
    Error('TKP: a contribution must be a proof-valued expression.',
          context)
  if world.IsTkp(name):
    return ('read', world.normalize(name),
            CallVariables(expression, context))
  anchor, resolved = ResolveToAnchor(expression, definitions, context)
  if anchor == 'TkpProbConjunction':
    fields = CallFields(resolved['call'])
    arguments = [fields[position]
                 for position in sorted(fields, key=FieldOrder)]
    if len(arguments) != 2:
      Error('TKP: TkpProbConjunction is binary.', context)
    return ('conj',
            BuildContributionTree(arguments[0], world, definitions,
                                  context),
            BuildContributionTree(arguments[1], world, definitions,
                                  context))
  Error('TKP: contribution of a proof-valued predicate must be a read '
        'or a conjunction; got %s.' % color.Warn(str(name)), context)


def TreeVariables(tree, result):
  if tree[0] == 'read':
    for variable in tree[2]:
      if variable not in result:
        result.append(variable)
  else:
    TreeVariables(tree[1], result)
    TreeVariables(tree[2], result)
  return result


def ContributionHeadVariables(contribution_rule, context):
  """Key variables of a contribution head, in canonical field order.

  The parser keeps head fields in source order; `P(b: y, a: x)` must
  still produce axes matching the member signature [a, b] -> [x, y]."""
  pairs = []
  for fv in contribution_rule['head']['record']['field_value']:
    if fv['field'] == 'logica_value':
      continue
    variable = VariableName(fv['value']['expression'])
    if variable is None:
      Error('TKP: keys of a proof-valued head must be variables.',
            context)
    pairs.append((fv['field'], variable))
  result = [variable for unused_field, variable in
            sorted(pairs, key=lambda pair: FieldOrder(pair[0]))]
  if len(set(result)) != len(result):
    Error('TKP: repeated variable in a proof-valued head %s; the '
          'diagonal mask is not implemented. Produce distinct key '
          'variables and equate them in a reader predicate.' %
          color.Warn(str(result)), context)
  return result


def InjectableNames(rules):
  """Injectable wrappers of the TKP world, anchors included.

  An injectable predicate is substituted into its callers during
  compilation and never exists as a table; the ones resolving into
  TKP anchors must not be grounded and are meaningless as cone
  inputs."""
  pairs = [(rule['head']['predicate_name'], rule) for rule in rules]
  definitions = FunctionalDefinitions(pairs)
  result = set(ANCHORS) | {'MergeList'}
  for name, candidates in definitions.items():
    if AnchorOf(name) is not None:
      result.add(name)
      continue
    if len(candidates) != 1 or name in result:
      continue
    head_fields = candidates[0]['head']['record']['field_value']
    synthetic_fields = []
    for fv in head_fields:
      if fv['field'] == 'logica_value':
        continue
      synthetic_fields.append(
          {'field': fv['field'], 'value': {'expression':
           {'variable': {'var_name': 'tkp_probe_%s' % fv['field']}}}})
    synthetic = {'call': {'predicate_name': name,
                          'record': {'field_value': synthetic_fields}}}
    try:
      anchor, unused = ResolveToAnchor(synthetic, definitions, name)
    except TkpCompileException:
      continue
    if anchor is not None:
      result.add(name)
  return result


###############################################################################
# VI. The plan facade.


class TkpPlan(object):
  """The TKP side of a neural target plan: the single bottleneck.

  Owns the world marking, the definitions, and the compiled TKP
  members. The numeric plan holds one instance and calls a handful of
  methods; everything proof-valued lives behind them."""

  def __init__(self, rules, normalize, diamond_suffix):
    self.world = ExtractTkpWorld(rules, normalize)
    self.definitions = FunctionalDefinitions(rules)
    self.members = {}
    self.diamond_suffix = diamond_suffix

  def Owns(self, name):
    return self.world.IsTkp(name)

  def RewriteRules(self, rules):
    """Rules with probability reads turned into relation reads."""
    if not self.world.probability_reads:
      return rules
    return [(name, RewriteProbabilityReads(rule, self.world,
                                           self.definitions))
            for name, rule in rules]

  def Signature(self, plan, predicate):
    """Key fields and classes; the value is a DNF, not a number."""
    signature = plan.PredicateSignature(predicate)
    key_fields = []
    key_classes = []
    for field in sorted(signature, key=FieldOrder):
      if field == 'logica_value':
        continue
      key_fields.append(field)
      key_classes.append(
          plan.program.column_classes.OfColumn(predicate, field))
    return key_fields, key_classes

  def CompileMember(self, plan, predicate):
    if predicate in self.members:
      return self.members[predicate]
    if predicate in self.world.atoms:
      member = TkpAtomMember(self.world.atoms[predicate])
    else:
      diamond = predicate + self.diamond_suffix
      source = (diamond
                if any(name == diamond for name, unused_rule,
                       unused_expression, unused_reads, unused_guards
                       in self.world.disjunction_rules)
                else predicate)
      contributions = []
      for name, rule, expression, unused_reads, guards in (
          self.world.disjunction_rules):
        if name != source:
          continue
        head_vars = ContributionHeadVariables(rule, predicate)
        tree = BuildContributionTree(expression, self.world,
                                     self.definitions, predicate)
        contributions.append((head_vars, tree, guards, rule))
      member = TkpDisjunctionMember(
          predicate, self.world.predicates[predicate], contributions)
    member.key_fields, member.key_types = self.Signature(plan, predicate)
    self.members[predicate] = member
    return member

  def ProbabilityMember(self, member):
    """The probability publisher of a member, or None when unread."""
    needed = set()
    for unused_owner, resolved in self.world.probability_reads:
      fields = CallFields(resolved['call'])
      argument = fields.get(0) if 0 in fields else fields.get('v')
      inner = CallName(argument)
      if inner:
        needed.add(inner)
    if member.name not in needed:
      return None
    return TkpProbabilityMember(member)

  def FactAxis(self, plan):
    """(probability predicate, fact row positions, fact count)."""
    atoms = sorted(self.world.atoms)
    if len(atoms) != 1:
      Error('TKP: exactly one fact predicate is supported for now; '
            'got %s.' % color.Warn(str(atoms)), plan.target)
    atom = self.world.atoms[atoms[0]]
    positions, unused_values = plan.input_rows[atom.body_relation]
    return (atom.probability_predicate, positions,
            int(positions[0].shape[0]))

  def CheckThetaSupport(self, plan, probe_state, environment, onp):
    """Every fact row must carry a probability; refuse at probe time.

    ThetaExt reads the probability values at the fact rows and ignores
    the support mask, so a fact whose probability predicate is
    undefined would silently get theta = 0: a proof-capable fact that
    does not exist on the SQL side, wasting slots and skewing
    inclusion-exclusion by rounding dust."""
    if not self.world.atoms:
      return
    predicate, positions, unused_n = self.FactAxis(plan)
    if predicate in probe_state:
      mask, unused_values = probe_state[predicate]
    else:
      mask, unused_values = environment[predicate]
    covered = onp.asarray(mask)[tuple(onp.asarray(p) for p in positions)]
    if not bool(onp.all(covered)):
      missing = int(covered.size - onp.sum(covered))
      Error('TKP: probability predicate %s is undefined for %d of %d '
            'fact rows of the atom body; a fact without a probability '
            'does not exist on the SQL side. Define %s on the whole '
            'body relation.' % (
                color.Warn(predicate), missing, covered.size,
                color.Warn(predicate)), plan.target)


###############################################################################
# VII. The sparse executor: a pure world solver and two seams.
#
# Solve(theta) computes the proofs of EVERY proof-valued predicate —
# python symbols, dictionaries {key indices: proofs} — unit by unit in
# stage order (which is topological): atoms are constant, recursion
# groups iterate to their fixpoint, standalone disjunctions settle in
# one confirmed pass. Determinism makes Solve a pure function of
# theta; a two-entry memo lets the forward and the backward of one
# training step share a single run.
#
# The seams publish probabilities onto the engines' tapes with the
# EXPLICIT polynomial derivative: on logix through its custom-gradient
# op (uncompiled training — the selection refreshes every step); on
# jax through pure_callback + custom_vjp, jit-compatible, so a real
# network in front of theta keeps its XLA speed.


class SparseTkpSolver(object):
  """The pure sparse solver of the TKP world."""

  def __init__(self, runtime):
    import numpy as onp
    self.onp = onp
    self.plan = runtime.plan
    self.tkp = self.plan.tkp
    (self.probability_predicate, positions,
     self.n_facts) = self.tkp.FactAxis(self.plan)
    self.row_positions = tuple(onp.asarray(p) for p in positions)
    self.atom_name = sorted(self.tkp.world.atoms)[0]
    self.atom_cells = {}
    for fact in range(self.n_facts):
      key = tuple(int(p[fact]) for p in self.row_positions)
      self.atom_cells[key] = [(fact,)]
    self.domains = runtime.domains
    self.units = []        # (compiled members, repetitions, unit names)
    self.unit_names = set()
    self.needed_guards = set()
    self.guard_rows = {}   # guard relation -> set of key tuples
    self.static_masks = {}
    self.cache = {}
    self.cache_order = []

  def EnsureUnit(self, members, repetitions):
    """Registers a fixpoint unit once; stage order is topological."""
    names = tuple(sorted(member.name for member in members))
    if names in self.unit_names:
      return
    self.unit_names.add(names)
    compiled = [(member,
                 [(head_vars, tree, guards)
                  for head_vars, tree, guards, unused_rule
                  in member.tkp_contributions])
                for member in members]
    for unused_member, trees in compiled:
      for unused_vars, unused_tree, guards in trees:
        self.needed_guards.update(
            guard_name for guard_name, unused_guard_vars in guards)
    self.units.append((compiled, repetitions, ', '.join(names)))

  def CaptureGuards(self, state, tensors):
    """Rows of the guard relations, captured when concrete.

    Guards are structural — independent of the learned parameters —
    so the probe's concrete capture serves every later (possibly
    traced) call. A guard whose relation never turns up concrete is a
    loud error at solving time."""
    onp = self.onp
    for name in sorted(self.needed_guards - set(self.guard_rows)):
      if name in state:
        mask = state[name][0]
      else:
        try:
          mask = tensors[name][0]
        except Exception:
          continue
      try:
        mask = onp.asarray(mask)
      except Exception:
        continue  # Traced; a concrete caller captures it first.
      self.guard_rows[name] = set(
          tuple(int(i) for i in key)
          for key in zip(*onp.nonzero(mask)))

  def ThetaTensor(self, state, tensors):
    """The fact probabilities: a differentiable gather at the rows."""
    if self.probability_predicate in state:
      unused_mask, values = state[self.probability_predicate]
    else:
      unused_mask, values = tensors[self.probability_predicate]
    return values[self.row_positions]

  def Solve(self, theta, stage='the current parameters'):
    """{member name: {key: proofs}} of the whole registered world."""
    signature = (theta, len(self.units))
    if signature in self.cache:
      return self.cache[signature]
    state = {self.atom_name: self.atom_cells}
    for compiled, repetitions, names in self.units:
      self.RunUnit(state, compiled, repetitions, names, theta, stage)
    self.cache[signature] = state
    self.cache_order.append(signature)
    while len(self.cache_order) > 2:  # forward + backward of a step
      del self.cache[self.cache_order.pop(0)]
    return state

  def RunUnit(self, state, compiled, repetitions, names, theta, stage):
    """One fixpoint unit; loud when the bound does not suffice.

    Truncation makes the sweep non-monotone: kept proofs may displace
    each other, so besides the fixpoint check the run watches for a
    REPEATED state — an oscillation would otherwise burn the whole
    bound and misreport as a plain timeout."""
    local = {member.name: {} for member, unused_compiled in compiled}
    seen = {self.Fingerprint(compiled, local): 0}
    converged = False
    for sweep in range(1, repetitions + 1):
      view = dict(state)
      view.update(local)
      new_local = {
          member.name: self.EvalMember(member, trees, view, theta)
          for member, trees in compiled}
      if new_local == local:
        converged = True
        break
      local = new_local
      fingerprint = self.Fingerprint(compiled, local)
      if fingerprint in seen:
        Error('Recursion of %s oscillates with period %d under %s '
              'instead of stabilizing; learning through dynamic '
              'equilibria is not supported yet.' % (
                  color.Warn(names), sweep - seen[fingerprint], stage),
              self.plan.target)
      seen[fingerprint] = sweep
    if not converged:
      Error('Recursion of %s does not stabilize within %d sweeps '
            'under %s; learning through dynamic equilibria is not '
            'supported yet.' % (color.Warn(names), repetitions, stage),
            self.plan.target)
    state.update(local)

  def Fingerprint(self, compiled, local):
    return tuple(
        (member.name, tuple(sorted(
            (key, tuple(proofs))
            for key, proofs in local[member.name].items())))
        for member, unused_trees in compiled)

  def EvalMember(self, member, trees, view, theta):
    pools = {}
    for head_vars, tree, guards in trees:
      filters = []
      for guard_name, guard_vars in guards:
        rows = self.guard_rows.get(guard_name)
        if rows is None:
          Error('TKP: the guard %s never materialized before '
                'solving; a guard must be a structural relation.' %
                color.Warn(guard_name), member.name)
        filters.append((guard_vars, rows))
      for assignment, proofs in self.EvalTree(tree, view, theta):
        if any(tuple(assignment[v] for v in guard_vars) not in rows
               for guard_vars, rows in filters):
          continue
        key = tuple(assignment[v] for v in head_vars)
        pools.setdefault(key, []).extend(proofs)
    return {key: SparseCanonicalize(pool, theta, member.k)
            for key, pool in pools.items()}

  def EvalTree(self, tree, view, theta):
    """[(variable assignment, proofs)] of a contribution tree."""
    if tree[0] == 'read':
      unused_kind, name, read_vars = tree
      return [(dict(zip(read_vars, key)), proofs)
              for key, proofs in view.get(name, {}).items()]
    left = self.EvalTree(tree[1], view, theta)
    right = self.EvalTree(tree[2], view, theta)
    if not left or not right:
      return []
    shared = sorted(set(left[0][0]) & set(right[0][0]))
    index = {}
    for assignment, proofs in right:
      index.setdefault(
          tuple(assignment[v] for v in shared), []).append(
              (assignment, proofs))
    result = []
    for assignment, proofs in left:
      for other, other_proofs in index.get(
          tuple(assignment[v] for v in shared), []):
        combined = SparseConjunction(proofs, other_proofs, theta)
        if combined:
          merged = dict(assignment)
          merged.update(other)
          result.append((merged, combined))
    return result

  def MemberShape(self, member):
    return tuple(len(self.domains[t]) for t in member.key_types)

  def StaticMask(self, member, theta=None):
    """The support mask of a member: structural, theta-independent.

    A cell holds proofs exactly when the structural join is nonempty
    (canonicalization never empties a nonempty pool), so the mask of
    any Solve serves all of them. The probe computes it first, with
    concrete theta; traced calls reuse it."""
    name = member.of_member.name if isinstance(
        member, TkpProbabilityMember) else member.name
    if name in self.static_masks:
      return self.static_masks[name]
    assert theta is not None, 'the probe computes masks first'
    onp = self.onp
    of_member = (member.of_member if isinstance(
        member, TkpProbabilityMember) else member)
    mask = onp.zeros(self.MemberShape(of_member), dtype=bool)
    for key in self.Solve(theta)[name]:
      mask[key] = True
    self.static_masks[name] = mask
    return mask

  def ProbabilityArray(self, member, theta, stage):
    onp = self.onp
    values = onp.zeros(self.MemberShape(member))
    cells = self.Solve(theta, stage)[member.of_member.name]
    for key, proofs in cells.items():
      values[key] = SparseProbability(proofs, theta)
    return values

  def GradientArray(self, member, theta, cotangent):
    """d(sum(cotangent * P)) / d theta, a vector over the facts."""
    onp = self.onp
    out = [0.0] * self.n_facts
    cotangent = onp.asarray(cotangent)
    cells = self.Solve(theta)[member.of_member.name]
    for key, proofs in cells.items():
      g = float(cotangent[key])
      if g != 0.0:
        SparseProbabilityGradient(proofs, theta, g, out)
    return onp.asarray(out)


def SolverOf(runtime):
  if runtime.tkp_solver is None:
    runtime.tkp_solver = SparseTkpSolver(runtime)
  return runtime.tkp_solver


def AtomFunction(runtime, member):
  """The atom member: only its support mask matters to the machinery."""
  import numpy as onp
  solver = SolverOf(runtime)
  mask = onp.zeros(solver.MemberShape(member), dtype=bool)
  for key in solver.atom_cells:
    mask[key] = True

  def EvaluateAtom(unused_state, unused_tensors):
    return (mask, None)

  return EvaluateAtom


def DisjunctionFunction(runtime, member):
  """A STANDALONE (non-recursive) disjunction registers its unit.

  It never reads itself, so one pass settles it (the second confirms);
  solving happens inside the probability seams — here only the
  structural mask is served."""
  solver = SolverOf(runtime)

  def EvaluateDisjunction(state, tensors):
    # Registration happens at evaluation: only genuine standalone
    # stages run this function (recursion groups register through
    # their own stage with their declared bound).
    solver.EnsureUnit([member], 2)
    solver.CaptureGuards(state, tensors)
    theta_tensor = solver.ThetaTensor(state, tensors)
    theta = ConcreteTheta(theta_tensor)
    return (solver.StaticMask(member, theta), None)

  return EvaluateDisjunction


def ConcreteTheta(theta_tensor):
  """Floats of a theta tensor, or None under a jax trace."""
  import numpy as onp
  try:
    return tuple(float(t) for t in onp.asarray(theta_tensor))
  except Exception:
    return None


def ProbabilityFunction(runtime, member):
  """The probability publisher: the custom-derivative seam.

  logix hosts the explicit polynomial derivative in its custom op and
  trains uncompiled; jax hosts it in pure_callback + custom_vjp and
  keeps jit for the tensor surroundings."""
  import numpy as onp
  solver = SolverOf(runtime)
  jnp = runtime.jnp
  shape = solver.MemberShape(member.of_member)

  def ForwardArray(theta_values, stage='the current parameters'):
    theta = tuple(float(t) for t in onp.asarray(theta_values))
    return solver.ProbabilityArray(member, theta, stage)

  def BackwardArray(cotangent, theta_values):
    theta = tuple(float(t) for t in onp.asarray(theta_values))
    return solver.GradientArray(member, theta, cotangent)

  if hasattr(jnp, 'custom'):  # The logix seam.

    def EvaluateLogix(state, tensors):
      solver.CaptureGuards(state, tensors)
      theta_tensor = solver.ThetaTensor(state, tensors)
      mask = solver.StaticMask(member, ConcreteTheta(theta_tensor))
      values = jnp.custom(
          ForwardArray,
          lambda cotangent, theta_values: [
              BackwardArray(cotangent, theta_values)],
          theta_tensor)
      return mask, values

    return EvaluateLogix

  engine = runtime.plan.tensor_engine_module  # The jax seam.

  def Published(theta_tensor):
    return engine.pure_callback(
        ForwardArray, engine.ShapeDtypeStruct(shape, onp.float64),
        theta_tensor)

  Published = engine.custom_vjp(Published)

  def PublishedForward(theta_tensor):
    return Published(theta_tensor), theta_tensor

  def PublishedBackward(theta_tensor, cotangent):
    return (engine.pure_callback(
        BackwardArray,
        engine.ShapeDtypeStruct((solver.n_facts,), onp.float64),
        cotangent, theta_tensor),)

  Published.defvjp(PublishedForward, PublishedBackward)

  def EvaluateJax(state, tensors):
    solver.CaptureGuards(state, tensors)
    theta_tensor = solver.ThetaTensor(state, tensors)
    mask = solver.StaticMask(member, ConcreteTheta(theta_tensor))
    return mask, Published(theta_tensor)

  return EvaluateJax


def MemberFunction(runtime, member):
  """Runtime function of a TKP member: the kind dispatch."""
  if isinstance(member, TkpProbabilityMember):
    return ProbabilityFunction(runtime, member)
  if isinstance(member, TkpAtomMember):
    return AtomFunction(runtime, member)
  return DisjunctionFunction(runtime, member)
