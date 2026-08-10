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

"""The tensor algebra of TKP against the reference tkp.py.

The safety net requested by the review: direct tests of TopK
(absorption, ties, FALSE slots, padding), Conjoin, Probability and the
subset/earlier axes — each checked against the reference
implementation, which itself is certified by the world-enumeration
oracle.

Run from examples/extensions:  PYTHONPATH=. python3 tkp_tests/tkp_tensor_test.py
"""

import random
import sys

import numpy as onp

sys.path.insert(0, '.')
sys.path.insert(0, '../..')

import tkp
from compiler import tkp_logica

(ProofProb, LexKeys, TopK, Conjoin, Probability,
 SlotValidity) = tkp_logica.MakeTensorOps(onp, onp)


def MakeIncidence(proofs, n):
  """Fact-index proofs -> incidence slots (c, n+1)."""
  slots = onp.zeros((len(proofs), n + 1))
  for position, proof in enumerate(proofs):
    for fact in proof:
      slots[position, fact] = 1.0
  return slots


def ReferenceValue(proofs, theta):
  """Fact-index proofs -> reference TKPValue (list of Proof)."""
  value = []
  for proof in proofs:
    facts = []
    for fact in sorted(proof):
      f = tkp.Fact()
      # Identities zero-padded so that the reference lexicographic
      # string order coincides with the numeric fact order.
      f.predicate = 'F'
      f.args = '%04d' % fact
      f.probability = float(theta[fact])
      facts.append(f)
    value.append(tkp.NewProof(facts))
  return value


def SlotsAsSets(slots):
  """Incidence slots -> list of fact-index frozensets, FALSE slots out."""
  result = []
  for row in slots:
    if row[-1] > 0:
      continue
    result.append(frozenset(int(i) for i in onp.nonzero(row)[0]))
  return result


def ReferenceAsSets(value):
  return [frozenset(int(f.args) for f in proof.facts) for proof in value]


def RandomProofs(rng, n, count):
  return [set(rng.sample(range(n), rng.randint(1, min(4, n))))
          for _ in range(count)]


def TestTopKAgainstReference(trials=300):
  """TopK == reference Canonicalize when probabilities are unique."""
  rng = random.Random(7)
  failures = 0
  for trial in range(trials):
    n = rng.randint(3, 9)
    k = rng.randint(1, 7)
    # Unique probabilities: no rank ties, so the orders must coincide
    # exactly. (Tie-breaks of the two sides are documented to differ up
    # to identity encodings; ties are exercised separately below.)
    theta = rng.sample(range(1, 1000), n)
    theta = onp.array([p / 1000.0 for p in theta])
    proofs = RandomProofs(rng, n, rng.randint(1, 10))
    theta_ext = onp.concatenate([theta, onp.zeros(1)])
    tensor_slots = TopK(MakeIncidence(proofs, n), theta_ext, k)
    tensor_sets = SlotsAsSets(tensor_slots)
    reference = tkp.TkpTop(ReferenceValue(proofs, theta), k)
    reference_sets = ReferenceAsSets(reference)
    if tensor_sets != reference_sets:
      failures += 1
      print('TOPK MISMATCH', trial, tensor_sets, reference_sets)
  return failures


def TestAbsorption():
  """A superset must be absorbed by its likelier subset."""
  n = 5
  theta_ext = onp.concatenate([onp.full(n, 0.5), onp.zeros(1)])
  slots = MakeIncidence([{0, 1, 2}, {0, 1}, {3}], n)
  top = TopK(slots, theta_ext, 3)
  survived = SlotsAsSets(top)
  assert survived == [frozenset({3}), frozenset({0, 1})], survived
  return 0


def TestFalsePadding():
  """Fewer candidates than k: FALSE slots pad, validity masks them."""
  n = 4
  theta_ext = onp.concatenate([onp.full(n, 0.5), onp.zeros(1)])
  top = TopK(MakeIncidence([{0}], n), theta_ext, 3)
  assert top.shape == (3, n + 1), top.shape
  validity = SlotValidity(top)
  assert list(validity) == [True, False, False], validity
  # The FALSE fact must keep padded slots out of the probability.
  probability = Probability(top, theta_ext, 3)
  assert abs(probability - 0.5) < 1e-12, probability
  return 0


def TestSubsetEarlierAxes():
  """The deterministic minimal regression of the earlier-axis bug.

  Found 2026-08-10 by this very net: `earlier` was tril(-1) — looking
  at LATER candidates — so real supersets were never absorbed and
  wasted top-k slots (probabilities hid it: a redundant superset
  cancels exactly in inclusion-exclusion). The orientation contract:
  the earlier (likelier) proof absorbs the later superset, never the
  other way around: {0} absorbs {0,1}; {0,1} must not absorb {0}."""
  n = 3
  theta_ext = onp.concatenate([onp.array([0.9, 0.1, 0.5]), onp.zeros(1)])
  top = TopK(MakeIncidence([{0, 1}, {0}], n), theta_ext, 2)
  survived = SlotsAsSets(top)
  assert survived == [frozenset({0})], survived
  return 0


def TestConjoinBroadcast():
  """Conjoin unions bit vectors across slot pairs."""
  n = 4
  a = MakeIncidence([{0}, {1}], n)
  b = MakeIncidence([{2}, {3}], n)
  u = Conjoin(a, b)
  assert SlotsAsSets(u) == [frozenset({0, 2}), frozenset({0, 3}),
                            frozenset({1, 2}), frozenset({1, 3})]
  return 0


def TestProbabilityAgainstReference(trials=200):
  """Tensor inclusion-exclusion == reference TkpProbability."""
  rng = random.Random(11)
  failures = 0
  for trial in range(trials):
    n = rng.randint(2, 8)
    theta = onp.array([rng.uniform(0.05, 0.95) for _ in range(n)])
    proofs = RandomProofs(rng, n, rng.randint(1, 6))
    reference = tkp.TkpTop(ReferenceValue(proofs, theta), 6)
    reference_probability = tkp.TkpProbability(reference)
    slots = MakeIncidence(ReferenceAsSets(reference), n)
    k = slots.shape[0]
    theta_ext = onp.concatenate([theta, onp.zeros(1)])
    tensor_probability = float(Probability(slots, theta_ext, k))
    if abs(tensor_probability - reference_probability) > 1e-9:
      failures += 1
      print('PROBABILITY MISMATCH', trial, tensor_probability,
            reference_probability)
  return failures


def TestTieBreakMinimal():
  """The deterministic minimal regression of the reversed tie-break.

  Found 2026-08-10 by Miss Vi's semantic review: LexKey weighted fact i
  by 2^-i and lexsort went ascending, so among equal-probability proofs
  the FACT ORDER WAS REVERSED relative to the reference ProofIdentity
  contract — and a reversed tie-break is not harmless: it changes which
  proofs survive truncation, hence the probability itself. Her minimum:
  {0,4} takes the first slot at .4; {0,2} and {1,3} tie at .3 for the
  second. The reference lexicographically keeps {0,2}: P = .4 + .3 -
  .4*.6/.8*.3... = .46; the reversed order kept the disjoint {1,3}:
  P = .7 - .12 = .58."""
  theta = onp.array([.5, .5, .6, .6, .8])
  proofs = [{0, 4}, {0, 2}, {1, 3}]
  n, k = 5, 2
  theta_ext = onp.concatenate([theta, onp.zeros(1)])
  slots = TopK(MakeIncidence(proofs, n), theta_ext, k)
  survived = SlotsAsSets(slots)
  assert survived == [frozenset({0, 4}), frozenset({0, 2})], survived
  probability = float(Probability(slots, theta_ext, k))
  assert abs(probability - 0.46) < 1e-9, probability
  return 0


def TestTiesAgainstReference(trials=300):
  """On ties TopK must follow the reference ProofIdentity order exactly.

  Random pools over few distinct probabilities — including exact 1.0,
  which makes a subset tie its own superset, exercising the prefix rule
  of the lexicographic order ({0} before {0,1}, like the shorter of two
  identity strings; the -1 sentinel in LexKeys). Identity encodings are
  zero-padded, so the reference string order IS the fact order and the
  parity must be exact."""
  rng = random.Random(13)
  failures = 0
  for trial in range(trials):
    n = rng.randint(3, 8)
    k = rng.randint(1, 6)
    values = [0.25, 0.5, 0.5, 0.5, 1.0]
    theta = onp.array([rng.choice(values) for _ in range(n)])
    proofs = RandomProofs(rng, n, rng.randint(1, 10))
    theta_ext = onp.concatenate([theta, onp.zeros(1)])
    tensor_sets = SlotsAsSets(TopK(MakeIncidence(proofs, n), theta_ext, k))
    reference_sets = ReferenceAsSets(
        tkp.TkpTop(ReferenceValue(proofs, theta), k))
    if tensor_sets != reference_sets:
      failures += 1
      print('TIE MISMATCH', trial, tensor_sets, reference_sets)
  return failures


def TestTieDeterminism():
  """Repeated canonicalization of a tied pool is bit-stable."""
  n = 6
  theta_ext = onp.concatenate([onp.full(n, 0.5), onp.zeros(1)])
  pool = MakeIncidence([{0, 1}, {2, 3}, {4, 5}, {1, 2}], n)
  first = TopK(pool, theta_ext, 2)
  for _ in range(5):
    again = TopK(onp.array(pool), theta_ext, 2)
    assert onp.array_equal(first, again)
  return 0


def TestNonPositiveKRefused():
  """k <= 0 must be a loud compile error on the neural side.

  The SQL Canonicalize reads k < 0 as "no truncation"; the tensor
  state has statically k slots, so before the check a negative k
  reached the Python slice [..., :k, :] and silently dropped
  candidates from the tail."""
  from parser_py import parse
  rules = parse.ParseFile(
      'T0P(x) = TkpTop(MergeList(x), 0); '
      'TNoLimit(x) = TkpTop(MergeList(x), -1); '
      'T4P(x) = TkpTop(MergeList(x), 4);')['rule']
  pairs = [(rule['head']['predicate_name'], rule) for rule in rules]
  definitions = tkp_logica.FunctionalDefinitions(pairs)
  assert tkp_logica.DisjunctionK('T4P', definitions, 'test') == 4
  for operator in ['T0P', 'TNoLimit']:
    try:
      tkp_logica.DisjunctionK(operator, definitions, 'test')
      assert False, 'k <= 0 of %s must be refused' % operator
    except tkp_logica.TkpCompileException:
      pass
  return 0


def TestCanonicalFieldOrder():
  """Heads and calls must sort fields with the one canonical key.

  The parser keeps `P(b: y, a: x)` in source order, and head axes
  built from it transposed silently against the member signature
  [a, b]; a str sort key would likewise put positional field 10
  before 2. Signature, CallVariables and ContributionHeadVariables
  all share FieldOrder now."""
  from parser_py import parse
  rule = parse.ParseFile('P(b: y, a: x) = 7;')['rule'][0]
  head_vars = tkp_logica.ContributionHeadVariables(rule, 'test')
  assert head_vars == ['x', 'y'], head_vars
  rule = parse.ParseFile('F() = Q(b: y, a: x);')['rule'][0]
  call = rule['head']['record']['field_value'][0]['value']['expression']
  call_vars = tkp_logica.CallVariables(call, 'test')
  assert call_vars == ['x', 'y'], call_vars
  order = sorted([10, 2, 'b', 'a'], key=tkp_logica.FieldOrder)
  assert order == [2, 10, 'a', 'b'], order
  return 0


def _ExpectCompileError(program, fragment):
  """The program must be refused with the fragment in the message."""
  from parser_py import parse
  rules = parse.ParseFile(program)['rule']
  pairs = [(rule['head']['predicate_name'], rule) for rule in rules]
  try:
    tkp_logica.ExtractTkpWorld(pairs)
  except tkp_logica.TkpCompileException as e:
    assert fragment in str(e), (fragment, str(e))
    return
  assert False, 'must be refused: %s' % program


def TestGuardsRefused():
  """Guards outside the structural skeleton are a loud compile error.

  The runtime materializes ALL rows of an atom's body relation and
  executes ONLY the value expression of a contribution; before the
  checks `... :- Raw(a, b), a != b` kept the self-edges and
  `Path(x, z) TKP= ... :- x != z` dropped the filter — both silently
  changing the meaning of the program."""
  atom = ('Edge(a, b) = TkpMakeFact(predicate: "e", args: [a, b], '
          'probability: P(a, b)) :- Raw(a, b)%s;')
  _ExpectCompileError(atom % ', a != b', 'guard or computation')
  _ExpectCompileError(atom % ', Other(a, b)', 'reads')
  disjunction = (
      'T2P(x) = TkpTop(MergeList(x), 2); '
      'Path(x, z) T2P= TkpProbConjunction(Path(x, y), Path(y, z)) '
      ':- x != z;')
  _ExpectCompileError(disjunction, 'guard or computation')
  return 0


def TestRepeatedVariablesRefused():
  """Diagonal unification is not implemented and must be refused."""
  from parser_py import parse
  rule = parse.ParseFile('P(x, x) = 7;')['rule'][0]
  try:
    tkp_logica.ContributionHeadVariables(rule, 'test')
    assert False, 'a repeated head variable must be refused'
  except tkp_logica.TkpCompileException as e:
    assert 'diagonal' in str(e)
  rule = parse.ParseFile('F() = Q(x, x);')['rule'][0]
  call = rule['head']['record']['field_value'][0]['value']['expression']
  try:
    tkp_logica.CallVariables(call, 'test')
    assert False, 'a repeated read variable must be refused'
  except tkp_logica.TkpCompileException as e:
    assert 'diagonal' in str(e)
  return 0


def TestThetaSupportChecked():
  """A fact row without a probability is refused at probe time.

  ThetaExt ignores the support mask of the probability predicate, so
  an undefined probability would silently read as theta = 0 — a
  proof-capable fact that does not exist on the SQL side."""
  from parser_py import parse
  rules = parse.ParseFile(
      'Edge(a, b) = TkpMakeFact(predicate: "e", args: [a, b], '
      'probability: EdgeProb(a, b)) :- Raw(a, b);')['rule']
  pairs = [(rule['head']['predicate_name'], rule) for rule in rules]
  plan = tkp_logica.TkpPlan(pairs, None, '_diamond')

  class StubPlan(object):
    input_rows = {'Raw': ((onp.array([0, 1]), onp.array([1, 0])), None)}
    target = 'test'

  mask = onp.zeros((2, 2), dtype=bool)
  mask[0, 1] = True
  mask[1, 0] = True
  full = {'EdgeProb': (mask, onp.full((2, 2), 0.5))}
  plan.CheckThetaSupport(StubPlan(), full, {}, onp)
  mask_holed = mask.copy()
  mask_holed[1, 0] = False
  holed = {'EdgeProb': (mask_holed, onp.full((2, 2), 0.5))}
  try:
    plan.CheckThetaSupport(StubPlan(), holed, {}, onp)
    assert False, 'a fact row without a probability must be refused'
  except tkp_logica.TkpCompileException as e:
    assert 'undefined for 1 of 2' in str(e), str(e)
  return 0


def TestThetaDependentHorizon():
  """Miss Vi's k=1 counterexample: the sweep horizon depends on theta.

  A star of direct edges v0->vi over a chain v0->v1->...->v9. Under
  theta favoring the direct edges the recursion stabilizes in a couple
  of sweeps — a probe would freeze a short horizon. Under theta
  favoring the chain the best proof of v9 is the full chain, which a
  linear recursion only builds after 9 sweeps: a forward truncated at
  the short horizon reports the wrong probability WITHOUT any error.
  Hence the contract: TKP loops train through the full user-declared
  @Recursive bound, and the probe (initial and post-training) only
  checks that the bound suffices."""
  chain, direct = 9, 8   # c_i: v_i->v_{i+1} (0..8); d_i: v0->v_i (2..9).
  n = chain + direct
  false_slot = onp.zeros(n + 1)
  false_slot[-1] = 1.0

  def Sweep(reach, theta_ext, k):
    new_reach = {}
    for v in range(1, 10):
      pool = [{9 + v - 2}] if v >= 2 else []   # The direct edge d_v.
      if v == 1:
        pool.append({0})                       # The chain edge c_0.
      slots = MakeIncidence(pool, n)
      if v >= 2:
        step = MakeIncidence([{v - 1}], n)     # The chain edge c_{v-1}.
        slots = onp.concatenate([slots, Conjoin(reach[v - 1], step)])
      new_reach[v] = TopK(slots, theta_ext, k)
    return new_reach

  def RunSweeps(theta_ext, count):
    reach = {v: onp.tile(false_slot, (1, 1)) for v in range(1, 10)}
    stable_at = None
    for sweep in range(1, count + 1):
      new_reach = Sweep(reach, theta_ext, 1)
      if stable_at is None and all(
          onp.array_equal(reach[v], new_reach[v]) for v in reach):
        stable_at = sweep
      reach = new_reach
    return reach, stable_at

  star = onp.concatenate(
      [onp.full(chain, 0.4), onp.full(direct, 0.9), onp.zeros(1)])
  unused_reach, stable_at = RunSweeps(star, 12)
  assert stable_at is not None and stable_at <= 3, stable_at
  frozen = stable_at + 2                       # The old probe contract.

  chainy = onp.concatenate(
      [onp.full(chain, 0.95), onp.full(direct, 0.05), onp.zeros(1)])
  truncated, unused = RunSweeps(chainy, frozen)
  full, full_stable = RunSweeps(chainy, 12)
  assert full_stable is not None and full_stable <= 12, full_stable
  # The frozen horizon still reports the (now unlikely) direct edge...
  assert SlotsAsSets(truncated[9]) == [frozenset({16})]
  # ...while the true fixpoint holds the full chain, at 12 times the
  # probability — a silent factor-of-12 error before the fix.
  assert SlotsAsSets(full[9]) == [frozenset(range(9))]
  p_truncated = float(Probability(truncated[9], chainy, 1))
  p_full = float(Probability(full[9], chainy, 1))
  assert abs(p_truncated - 0.05) < 1e-9, p_truncated
  assert abs(p_full - 0.95 ** 9) < 1e-9, p_full
  return 0


def TestTruncationLossContract():
  """The documented approximation contract of losses on truncated DNF.

  This is a CONTRACT, not a failure: TkpProbability is exact over the
  STORED proofs, so on a truncated DNF the positive loss -log(P) is
  conservative (over-penalizes) and the negative loss -log(1-P) is
  optimistic — dropped proofs go unpenalized. Miss Vi's scale example:
  100 independent single-fact proofs of 0.1 at k=1 store P = .1, while
  the full space has P = 1 - .9^100 — the stored negative loss is two
  orders of magnitude below the true one."""
  import math
  n = 100
  theta_ext = onp.concatenate([onp.full(n, 0.1), onp.zeros(1)])
  slots = TopK(MakeIncidence([{i} for i in range(n)], n), theta_ext, 1)
  p_stored = float(Probability(slots, theta_ext, 1))
  assert abs(p_stored - 0.1) < 1e-12, p_stored
  p_full = 1.0 - 0.9 ** n
  assert -math.log(p_stored) >= -math.log(p_full)          # Conservative.
  assert -math.log(1 - p_stored) <= -math.log(1 - p_full)  # Optimistic.
  assert -math.log(1 - p_full) / -math.log(1 - p_stored) > 100
  return 0


def TestWhackTheTop():
  """Negative training on truncated DNF suppresses routes SEQUENTIALLY.

  Each step the gradient of -log(1-P) reaches only the stored top-1
  proof; a suppressed route drops out and the next one surfaces into
  the slot. Neither an instant failure nor a guaranteed rescue: after
  a few steps most of the mass still hides below the cut untouched,
  after enough steps every route has been pushed down."""
  n = 5
  theta = onp.full(n, 0.5)
  pools = [{i} for i in range(n)]

  def Step(theta):
    theta_ext = onp.concatenate([theta, onp.zeros(1)])
    slots = TopK(MakeIncidence(pools, n), theta_ext, 1)
    (stored,) = SlotsAsSets(slots)
    (fact,) = stored
    updated = theta.copy()
    # d(-log(1 - theta_f)) / d theta_f = 1 / (1 - theta_f).
    updated[fact] -= 0.1 * 1.0 / (1.0 - theta[fact])
    return updated

  for unused_step in range(3):
    theta = Step(theta)
  # One route per step: after 3 steps exactly n - 3 hide untouched.
  assert onp.sum(theta == 0.5) == n - 3, theta
  for unused_step in range(40):
    theta = Step(theta)
  assert onp.all(theta < 0.4), theta            # Eventually all pushed.
  return 0


def TestIsFunctionalUncompilable():
  """The general-machinery hole found through TKP: an uncompilable rule.

  Before: ExtractRuleStructure raising made IsFunctional answer False —
  "materializable" — so auto-grounding tried to build a table of a
  substitution-only predicate and crashed (the historical MakeFact
  ground-and-crash). After: uncompilable standalone means walk-through."""
  from compiler import neural_logica
  from parser_py import parse
  rules = parse.ParseFile(
      'Wrapper(predicate:, args:, probability:) = '
      '[{facts: [{predicate:, args:, probability:}]}];')['rule']
  rules_of = {'Wrapper': rules}
  assert neural_logica.IsFunctional('Wrapper', rules_of), (
      'an uncompilable standalone rule must be treated as injected')
  return 0


def main():
  failures = 0
  failures += TestTopKAgainstReference()
  failures += TestAbsorption()
  failures += TestFalsePadding()
  failures += TestSubsetEarlierAxes()
  failures += TestConjoinBroadcast()
  failures += TestProbabilityAgainstReference()
  failures += TestTieBreakMinimal()
  failures += TestTiesAgainstReference()
  failures += TestTieDeterminism()
  failures += TestNonPositiveKRefused()
  failures += TestCanonicalFieldOrder()
  failures += TestGuardsRefused()
  failures += TestRepeatedVariablesRefused()
  failures += TestThetaSupportChecked()
  failures += TestThetaDependentHorizon()
  failures += TestTruncationLossContract()
  failures += TestWhackTheTop()
  failures += TestIsFunctionalUncompilable()
  print('tkp_tensor_test: failures: %d' % failures)
  return 1 if failures else 0


if __name__ == '__main__':
  sys.exit(main())
