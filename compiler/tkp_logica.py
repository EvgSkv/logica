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
    self.disjunction_rules = []   # (name, rule, expression, reads)
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
    # A single rule: the value is in the head or in a body unification.
    for conjunct in conjuncts:
      unification = conjunct.get('unification')
      if unification is None:
        continue
      left = unification['left_hand_side']
      if VariableName(left) == 'logica_value':
        return [(rule, unification['right_hand_side'])]
    return [(rule, None)]

  def CheckContributionBody(contribution_rule, read_names, name):
    """Refuses guards in a contribution body.

    The runtime compiles the VALUE EXPRESSION of a contribution only:
    proof reads join by their variables and nothing else executes, so
    a comparison, an unrelated predicate or a computation in the body
    would be silently dropped, changing the meaning of the program.
    Allowed: the aggregation machinery (_MultBodyAggAux), the
    logica_value binding, and body restatements of the very reads of
    the value expression."""
    conjuncts = (contribution_rule.get('body') or {}).get(
        'conjunction', {}).get('conjunct', [])
    for conjunct in conjuncts:
      predicate = conjunct.get('predicate', {}).get('predicate_name')
      if predicate is not None and predicate[:1].isalpha():
        if '_MultBodyAggAux' in predicate:
          continue
        if world.normalize(predicate) in read_names:
          continue
        Error('TKP: contribution of %s reads %s in its body; the '
              'runtime executes only the value expression, so a body '
              'guard would be silently ignored. Move the filter into '
              'a separate predicate feeding the proof reads.' % (
                  color.Warn(name), color.Warn(predicate)), name)
      unification = conjunct.get('unification')
      if (unification is not None and VariableName(
          unification['left_hand_side']) == 'logica_value'):
        continue
      Error('TKP: contribution of %s has a guard or computation in '
            'its body; the runtime executes only the value '
            'expression, so it would be silently ignored. Move the '
            'filter into a separate predicate feeding the proof '
            'reads.' % color.Warn(name), name)

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
      CheckContributionBody(rule, set(), name)
    for contribution_rule, expression in contributions:
      reads = []
      read_names = set()
      if expression is not None:
        TkpReadsOf(expression, world, definitions, name, reads)
        for kind, read in reads:
          if kind == 'read':
            read_names.add(world.normalize(CallName(read)))
      CheckContributionBody(contribution_rule, read_names, name)
      if expression is None:
        Error('TKP: cannot find the contribution of %s.' %
              color.Warn(name), name)
      world.disjunction_rules.append(
          (name, contribution_rule, expression, reads))

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
# V. Member classes and the tensor algebra.
#
# A proof is stored SPARSELY: a slot is an ascending vector of L fact
# ids, L = min(n_facts, tkp_max_proof_length of @Engine). Real facts
# are 0..n-1; three virtual ids follow:
#   n     FALSE  — a dead or empty slot, probability 0;
#   n+1   PAD    — past the end of the proof, probability 1;
#   n+2   POISON — a slot that overflowed its capacity, probability
#          NaN. A compiled training step cannot raise, so the overflow
#          is sticky-loud instead: the poisoned slot outranks
#          everything, the loss turns NaN, and the training loop
#          diagnoses the NaN with an eager re-probe — where the same
#          overflow raises TkpCapacityError with the precise message.
# theta_ext = fact probabilities extended with [0, 1, NaN]; the ops
# recover n_facts from its length. The state value of a TKP member:
# (mask over keys, slot ids of shape (keys..., slots, L), int32).
# Capacity limits only STORED proofs; the unions inside the
# inclusion-exclusion are transient and never truncated.


class TkpCapacityError(TkpCompileException):
  """A proof does not fit the configured tkp_max_proof_length."""


def MakeTensorOps(jnp, onp):
  """Operations over sparse proof slots.

  Every operation receives theta_ext of length n_facts + 3; the
  capacity L is the trailing dimension of the slot ids themselves.
  Slots are ascending; the virtual ids (FALSE < PAD < POISON) sort
  after the real facts, except that POISON slots are normalized to
  [POISON, PAD...] so the mark survives any truncation."""

  def Virtual(theta_ext):
    n = int(theta_ext.shape[-1]) - 3
    return n, n + 1, n + 2

  def FirstMask(ids):
    """First occurrence of each id in an ascending slot."""
    head = onp.ones(tuple(ids.shape[:-1]) + (1,), dtype=bool)
    return jnp.concatenate([head, ids[..., 1:] != ids[..., :-1]],
                           axis=-1)

  def Theta(ids, theta_ext):
    """theta at the slot ids, via a LIVE index (ids change per step)."""
    spread = jnp.broadcast_to(theta_ext,
                              ids.shape[:-1] + theta_ext.shape[-1:])
    return jnp.take_along_axis(spread, ids, -1)

  def ProofProb(ids, theta_ext):
    """Differentiable probability of ascending slots: (..., L) -> (...).

    Duplicates (unions concatenate before sorting) count once through
    the first-occurrence mask; PAD contributes log(1) = 0, FALSE sinks
    the product to ~0, POISON turns it NaN. The summation runs in
    ascending fact order — bit-identical to the dense representation."""
    t = Theta(ids, theta_ext)
    return jnp.exp(jnp.sum(
        jnp.where(FirstMask(ids), jnp.log(t + 1e-30), 0.0), axis=-1))

  def RankProb(ids, theta_ext):
    """Exact product probability, for RANKING only.

    Multiplies theta directly (an exact 1.0 per PAD), so that
    coincidentally equal products — 0.25*1.0 against 0.5*0.5 — tie
    bit-exactly, as they do in the reference, and fall through to the
    lexicographic keys. Ranks carry no gradient (they only pick
    slots), so the product needs no gradient rule."""
    t = Theta(ids, theta_ext)
    return jnp.prod(jnp.where(FirstMask(ids), t, 1.0), axis=-1)

  def LexKeys(ids, false_id):
    """Tie-break keys realizing the reference ProofIdentity order.

    An ascending slot IS the positional key vector; every virtual id
    maps to the -1 sentinel, so a proof that is a prefix of another
    sorts first, exactly like the shorter of two identity strings.
    Returns a tuple of keys, most significant first, for jnp.lexsort
    (which wants its primary key LAST)."""
    keys = jnp.where(ids >= false_id, -1, ids)
    return tuple(keys[..., i]
                 for i in reversed(range(int(ids.shape[-1]))))

  def Rows(length, false_id, pad_id, poison_id):
    false_row = onp.full(length, pad_id, dtype=onp.int32)
    false_row[0] = false_id
    poison_row = onp.full(length, pad_id, dtype=onp.int32)
    poison_row[0] = poison_id
    return false_row, poison_row

  def Conjoin(a, b, theta_ext):
    """(..., ka, L) x (..., kb, L) -> (..., ka*kb, L): sorted union.

    A union containing FALSE is dead: it collapses to the pure FALSE
    slot (so its real ids do not count against capacity), and a union
    inheriting POISON stays POISON. A union of more than L real facts
    cannot be stored: eagerly that raises TkpCapacityError; inside a
    compiled step the slot turns POISON instead."""
    false_id, pad_id, poison_id = Virtual(theta_ext)
    length = int(a.shape[-1])
    ka, kb = int(a.shape[-2]), int(b.shape[-2])
    base = tuple(a.shape[:-2])
    u = jnp.concatenate([
        jnp.broadcast_to(a[..., :, None, :], base + (ka, kb, length)),
        jnp.broadcast_to(b[..., None, :, :], base + (ka, kb, length)),
    ], axis=-1)
    u = u.reshape(base + (ka * kb, 2 * length))
    s = jnp.sort(u, axis=-1)
    s = jnp.where(FirstMask(s), s, pad_id)
    false_row, poison_row = Rows(2 * length, false_id, pad_id, poison_id)
    dead = jnp.any(s == false_id, axis=-1)
    s = jnp.where(dead[..., None], false_row, s)
    s = jnp.sort(s, axis=-1)
    overflow = jnp.sum(jnp.where(s < false_id, 1, 0), axis=-1) > length
    poisoned = overflow | jnp.any(s == poison_id, axis=-1)
    s = jnp.where(poisoned[..., None], poison_row, s)
    LoudCapacity(overflow, length)
    return s[..., :length]

  def LoudCapacity(overflow, length):
    """Raise on overflow when the value is concrete (eager or probe).

    Under a jax trace the bool() conversion throws and the POISON path
    stays in charge; the compiled-cache path of logix likewise relies
    on POISON, since a trace-time check would bake into the cache."""
    try:
      flagged = bool(jnp.any(overflow))
    except TypeError:
      return
    if flagged:
      raise TkpCapacityError(
          'TKP: proof capacity exceeded — a conjunction built a proof '
          'of more than %d facts. Raise tkp_max_proof_length of '
          '@Engine (or set it, if absent).' % length, 'TKP runtime')

  def TopK(candidates, theta_ext, k):
    """(..., c, L) -> (..., k, L): the reference greedy canonicalization.

    Candidates presort canonically (probability desc, lexicographic
    ties); then k rounds each keep the first live candidate and retire
    its supersets — absorption exactly as the reference Canonicalize,
    where only KEPT proofs absorb. The subset test is one sorted merge:
    a kept proof is a subset of a candidate exactly when their union
    holds no more distinct non-virtual ids than the candidate (FALSE
    participates like a fact, PAD and POISON are vacuous). Cost is
    k * c * 2L with no pairwise candidate matrix — a c^2 * L^2
    broadcast here once materialized 160 GB on a 5x5 grid world.
    Fewer than k live candidates pad the tail with FALSE slots."""
    false_id, pad_id, poison_id = Virtual(theta_ext)
    length = int(candidates.shape[-1])
    probs = RankProb(candidates, theta_ext)
    probs = jnp.where(probs != probs, onp.inf, probs)  # POISON outranks.
    order = jnp.lexsort(LexKeys(candidates, false_id) + (-probs,),
                        axis=-1)
    ids = jnp.take_along_axis(candidates, order[..., None], axis=-2)
    false_row, unused_poison_row = Rows(length, false_id, pad_id,
                                        poison_id)
    occupancy = jnp.sum(jnp.where(ids <= false_id, 1, 0), axis=-1)
    alive = onp.ones(tuple(ids.shape[:-1]), dtype=bool)
    kept_slots = []
    for unused_round in range(k):
      first = alive & (jnp.cumsum(jnp.where(alive, 1, 0), axis=-1) == 1)
      any_alive = jnp.any(alive, axis=-1)
      kept = jnp.max(jnp.where(first[..., None], ids, -1), axis=-2)
      kept = jnp.where(any_alive[..., None], kept, false_row)
      kept_slots.append(kept[..., None, :])
      union = jnp.sort(jnp.concatenate(
          [jnp.broadcast_to(kept[..., None, :], tuple(ids.shape)), ids],
          axis=-1), axis=-1)
      grown = jnp.sum(
          jnp.where(FirstMask(union) & (union <= false_id), 1, 0),
          axis=-1)
      # The kept proof absorbs (and itself retires) where it grew
      # nothing; the exhausted cells have alive already empty.
      alive = alive & (grown != occupancy)
    return jnp.concatenate(kept_slots, axis=-2)

  def Probability(slots, theta_ext, k):
    """(..., k, L) -> (...): inclusion-exclusion, 2^k - 1 terms.

    Unions are transient (r*L ids, sorted, duplicates masked inside
    ProofProb) — the storage capacity does not bound them."""
    import itertools
    total = 0.0
    for r in range(1, k + 1):
      for subset in itertools.combinations(range(k), r):
        union = jnp.sort(
            slots[..., list(subset), :].reshape(
                slots.shape[:-2] + (r * int(slots.shape[-1]),)),
            axis=-1)
        total = total + (-1.0) ** (r + 1) * ProofProb(union, theta_ext)
    return total

  def SlotValidity(slots, theta_ext):
    """A slot is real when it has no FALSE id and is nonempty.

    A POISON slot counts as valid: its NaN must reach the loss."""
    false_id, pad_id, unused_poison_id = Virtual(theta_ext)
    has_false = jnp.any(slots == false_id, axis=-1)
    nonempty = jnp.any(slots != pad_id, axis=-1)
    return (~has_false) & nonempty

  return ProofProb, LexKeys, TopK, Conjoin, Probability, SlotValidity


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
    self.tkp_contributions = contributions  # (head_vars, tree, rule)


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
                       unused_expression, unused_reads
                       in self.world.disjunction_rules)
                else predicate)
      contributions = []
      for name, rule, expression, unused_reads in (
          self.world.disjunction_rules):
        if name != source:
          continue
        head_vars = ContributionHeadVariables(rule, predicate)
        tree = BuildContributionTree(expression, self.world,
                                     self.definitions, predicate)
        contributions.append((head_vars, tree, rule))
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

  def ProofLength(self, plan, n_facts):
    """The slot capacity L = min(n_facts, tkp_max_proof_length).

    tkp_max_proof_length lives in @Engine next to tensor_engine. It is
    a storage capacity, never a semantic truncation: a real proof
    beyond it is a loud TkpCapacityError. Without it L = n_facts — the
    proven ceiling (a proof is a set) — which on a large world makes
    the sparse layout as heavy as the dense one; hence the warning."""
    settings = plan.program.annotations.annotations.get(
        '@Engine', {}).get(plan.engine, {})
    cap = settings.get('tkp_max_proof_length')
    if cap is None:
      if n_facts > 64 and not getattr(self, 'warned_capacity', False):
        self.warned_capacity = True
        print('Warning: TKP stores proofs of up to %d facts (the '
              'whole fact axis); set tkp_max_proof_length in @Engine '
              'to bound the slot capacity.' % n_facts)
      return n_facts
    return min(n_facts, int(cap))

  def FalseSlot(self, plan, onp):
    """[FALSE, PAD, PAD, ...] of the world's capacity."""
    unused_p, unused_positions, n_facts = self.FactAxis(plan)
    length = self.ProofLength(plan, n_facts)
    slot = onp.full(length, n_facts + 1, dtype=onp.int32)
    slot[0] = n_facts
    return slot

  def EmptyState(self, plan, member, domains, jnp, onp):
    """The empty loop state of a TKP member: all slots FALSE."""
    shape = tuple(len(domains[t]) for t in member.key_types)
    false_slot = self.FalseSlot(plan, onp)
    values = jnp.broadcast_to(jnp.asarray(false_slot),
                              shape + (member.slots, len(false_slot)))
    return (jnp.zeros(shape, dtype=bool), values)



###############################################################################
# VII. Runtime compilers: one per member kind, sharing a small context.
#
# The state contract: a TKP member's state entry is a pair
#   (mask over keys..., slot ids of shape (keys..., slots, L)),
# with the id vocabulary of section V (facts, FALSE, PAD, POISON).
# theta_ext is the fact probability vector extended with [0, 1, NaN].


class _RuntimeContext(object):
  """Shared pieces of the TKP runtime: ops, fact axis, state access."""

  def __init__(self, runtime):
    import numpy as onp
    self.onp = onp
    self.jnp = runtime.jnp
    self.runtime = runtime
    self.plan = runtime.plan
    self.tkp = self.plan.tkp
    (self.ProofProb, self.LexKeys, self.TopK, self.Conjoin,
     self.Probability, self.SlotValidity) = MakeTensorOps(self.jnp, onp)
    (self.probability_predicate, positions,
     self.n_facts) = self.tkp.FactAxis(self.plan)
    self.row_positions = tuple(onp.asarray(p) for p in positions)
    self.proof_length = self.tkp.ProofLength(self.plan, self.n_facts)
    self.false_slot = self.tkp.FalseSlot(self.plan, onp)

  def ThetaExt(self, state, tensors):
    """Fact probabilities at the fact rows, virtual ids appended.

    Shape: (n_facts + 3,) — [facts..., FALSE 0, PAD 1, POISON NaN].
    Differentiable: the values come from the probability predicate's
    tensor (parameters overlay or cone state)."""
    if self.probability_predicate in state:
      unused_mask, values = state[self.probability_predicate]
    else:
      unused_mask, values = tensors[self.probability_predicate]
    theta = values[self.row_positions]
    virtual = self.onp.array([0.0, 1.0, self.onp.nan])
    return self.jnp.concatenate([theta, self.jnp.asarray(virtual)])

  def RankTheta(self, state, tensors):
    """ThetaExt for the sweep phase: values only, the gradient cut.

    Sweeps rank and select — their outputs are proof ids, structurally
    outside the gradient; the loss recomputes probabilities from theta
    afterwards. Cutting theta at the SCAN ENTRY (not the exit) is what
    lets jax skip saving per-sweep linearization residuals, which once
    cost gigabytes; logix achieves the same by suspending its tape."""
    theta_ext = self.ThetaExt(state, tensors)
    engine = getattr(self.plan, 'tensor_engine_module', None)
    stop = getattr(getattr(engine, 'lax', None), 'stop_gradient', None)
    if stop is not None:
      return stop(theta_ext)
    return theta_ext

  def ReadTkp(self, name, state, tensors):
    """A TKP member's (mask, incidences): loop portal, state, tensors."""
    member = self.tkp.members.get(name)
    if member is not None and member.portal in state:
      return state[member.portal]
    if name in state:
      return state[name]
    return tensors[name]


def _AtomFunction(context, member):
  """The atom: a frozen base of one-fact proofs.

  Output: mask (keys...), slot ids (keys..., 1, L) — the single slot
  of a fact row is [row id, PAD...]; absent cells hold FALSE."""
  onp = context.onp
  jnp = context.jnp
  shape = tuple(len(context.runtime.domains[t])
                for t in member.key_types)
  base_mask = onp.zeros(shape, dtype=bool)
  base_ids = onp.tile(context.false_slot, shape + (1, 1))
  base_mask[context.row_positions] = True
  # Positions 1+ hold PAD already (the tail of the FALSE slot).
  base_ids[context.row_positions + (0, 0)] = onp.arange(context.n_facts)
  frozen = (jnp.asarray(base_mask), jnp.asarray(base_ids))

  def EvaluateAtom(unused_state, unused_tensors):
    return frozen

  return EvaluateAtom


def _ProbabilityFunction(context, member):
  """The probability publisher: DNF member state -> Num relation.

  Output: mask (keys...), probabilities (keys...) — the exact
  inclusion-exclusion over the member's slots at current theta."""
  of_member = member.of_member

  def EvaluateProbability(state, tensors):
    mask, incidences = context.ReadTkp(of_member.name, state, tensors)
    theta_ext = context.ThetaExt(state, tensors)
    probability = context.Probability(incidences, theta_ext,
                                      int(incidences.shape[-2]))
    return mask, probability

  return EvaluateProbability


def _DisjunctionFunction(context, member):
  """The disjunction: contributions -> candidate pool -> absorb, top-k.

  Each contribution is evaluated over axes = head vars + join vars;
  join axes fold into the candidate axis, pools concatenate, and TopK
  keeps member.k slots per head cell."""
  jnp = context.jnp

  compiled = []
  for head_vars, tree, unused_rule in member.tkp_contributions:
    variables = TreeVariables(tree, [])
    join_vars = [v for v in variables if v not in head_vars]
    axes = list(head_vars) + join_vars
    variable_class = {}

    def CollectClasses(node):
      if node[0] == 'read':
        read_member = context.tkp.members.get(node[1])
        for position, variable in enumerate(node[2]):
          variable_class.setdefault(
              variable, read_member.key_types[position])
      else:
        CollectClasses(node[1])
        CollectClasses(node[2])
    CollectClasses(tree)
    compiled.append((axes, len(head_vars), tree, variable_class))

  def AlignRead(node, axes, axis_sizes, state, tensors):
    """A member read aligned to the contribution axes.

    Input slot ids: (read keys..., s, L); output:
    (axis_sizes..., s, L) — read axes permuted into their positions
    among `axes`, missing axes broadcast."""
    unused_name, read_vars = node[1], node[2]
    unused_mask, incidences = context.ReadTkp(node[1], state, tensors)
    order = sorted(range(len(read_vars)),
                   key=lambda i: axes.index(read_vars[i]))
    incidences = jnp.transpose(
        incidences,
        tuple(order) + (len(read_vars), len(read_vars) + 1))
    expanded_shape = []
    source_dim = 0
    for variable in axes:
      if variable in read_vars:
        expanded_shape.append(incidences.shape[source_dim])
        source_dim += 1
      else:
        expanded_shape.append(1)
    incidences = incidences.reshape(
        tuple(expanded_shape) + incidences.shape[-2:])
    target = tuple(axis_sizes) + incidences.shape[-2:]
    return jnp.broadcast_to(incidences, target)

  def EvalTree(node, axes, axis_sizes, state, tensors, theta_ext):
    """A contribution tree -> candidates (axis_sizes..., c, L)."""
    if node[0] == 'read':
      return AlignRead(node, axes, axis_sizes, state, tensors)
    left = EvalTree(node[1], axes, axis_sizes, state, tensors,
                    theta_ext)
    right = EvalTree(node[2], axes, axis_sizes, state, tensors,
                     theta_ext)
    return context.Conjoin(left, right, theta_ext)

  def EvaluateDisjunction(state, tensors):
    theta_ext = context.RankTheta(state, tensors)
    pools = []
    for axes, head_count, tree, variable_class in compiled:
      axis_sizes = [len(context.runtime.domains[variable_class[v]])
                    for v in axes]
      candidates = EvalTree(tree, axes, axis_sizes, state, tensors,
                            theta_ext)
      join_count = len(axes) - head_count
      if join_count:  # Join axes fold into the candidate axis.
        candidates = candidates.reshape(
            candidates.shape[:head_count] + (-1, candidates.shape[-1]))
      pools.append(candidates)
    pool = jnp.concatenate(pools, axis=-2)
    new_incidences = context.TopK(pool, theta_ext, member.k)
    mask = jnp.any(context.SlotValidity(new_incidences, theta_ext),
                   axis=-1)
    return mask, new_incidences

  return EvaluateDisjunction


def MemberFunction(runtime, member):
  """Runtime function of a TKP member: the kind dispatch."""
  context = _RuntimeContext(runtime)
  if isinstance(member, TkpProbabilityMember):
    return _ProbabilityFunction(context, member)
  if isinstance(member, TkpAtomMember):
    return _AtomFunction(context, member)
  return _DisjunctionFunction(context, member)
