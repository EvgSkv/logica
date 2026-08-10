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

"""The sparse proof algebra of TKP against the reference tkp.py.

The safety net of the reviews: the sparse canonicalization is a
REIMPLEMENTATION of the reference (the compiler cannot import the
examples tree), so parity is proven proof-for-proof, IN ORDER, on
random pools — plus the explicit polynomial gradient against central
differences, and the compile-layer restrictions.

Run from examples/extensions:  PYTHONPATH=.:../.. python3 tkp_tests/tkp_tensor_test.py
"""

import random
import sys

import numpy as onp

sys.path.insert(0, '.')
sys.path.insert(0, '../..')

import tkp
from compiler import tkp_logica

Canonicalize = tkp_logica.SparseCanonicalize
Conjunction = tkp_logica.SparseConjunction
Probability = tkp_logica.SparseProbability
Gradient = tkp_logica.SparseProbabilityGradient


def Proofs(pools):
  """Fact-index sets -> sorted proof tuples."""
  return [tuple(sorted(proof)) for proof in pools]


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


def ReferenceAsLists(value):
  """Reference proofs -> fact tuples, PRESERVING the canonical order."""
  return [tuple(sorted(int(f.args) for f in proof.facts))
          for proof in value]


def RandomProofs(rng, n, count):
  return [set(rng.sample(range(n), rng.randint(1, min(4, n))))
          for _ in range(count)]


def TestCanonicalizeAgainstReference(trials=300):
  """Proof-for-proof, IN ORDER, on random pools with unique thetas."""
  rng = random.Random(7)
  failures = 0
  for trial in range(trials):
    n = rng.randint(3, 9)
    k = rng.randint(1, 7)
    theta = rng.sample(range(1, 1000), n)
    theta = [p / 1000.0 for p in theta]
    proofs = RandomProofs(rng, n, rng.randint(1, 10))
    ours = Canonicalize(Proofs(proofs), theta, k)
    reference = ReferenceAsLists(
        tkp.TkpTop(ReferenceValue(proofs, theta), k))
    if ours != reference:
      failures += 1
      print('CANONICALIZE MISMATCH', trial, ours, reference)
  return failures


def TestTiesAgainstReference(trials=300):
  """On ties the canonical order must match the reference exactly.

  Few distinct probability values — including exact 1.0, which makes
  a subset tie its own superset, exercising the prefix rule (python
  tuple comparison: a shorter prefix sorts first, like the shorter of
  two identity strings)."""
  rng = random.Random(13)
  failures = 0
  for trial in range(trials):
    n = rng.randint(3, 8)
    k = rng.randint(1, 6)
    values = [0.25, 0.5, 0.5, 0.5, 1.0]
    theta = [rng.choice(values) for _ in range(n)]
    proofs = RandomProofs(rng, n, rng.randint(1, 10))
    ours = Canonicalize(Proofs(proofs), theta, k)
    reference = ReferenceAsLists(
        tkp.TkpTop(ReferenceValue(proofs, theta), k))
    if ours != reference:
      failures += 1
      print('TIE MISMATCH', trial, ours, reference)
  return failures


def TestAbsorption():
  """A superset must be absorbed by its likelier subset — and never
  the other way around (the earlier-axis bug of the tensor days:
  {0} absorbs {0,1}; {0,1} must not absorb {0})."""
  theta = [0.5] * 5
  kept = Canonicalize(Proofs([{0, 1, 2}, {0, 1}, {3}]), theta, 3)
  assert kept == [(3,), (0, 1)], kept
  theta = [0.9, 0.1, 0.5]
  kept = Canonicalize(Proofs([{0, 1}, {0}]), theta, 2)
  assert kept == [(0,)], kept
  return 0


def TestConjunction():
  """All pair unions, canonical, no truncation."""
  theta = [0.5] * 4
  u = Conjunction(Proofs([{0}, {1}]), Proofs([{2}, {3}]), theta)
  assert sorted(u) == [(0, 2), (0, 3), (1, 2), (1, 3)], u
  # A conjunction with a duplicated fact dedups inside the proof.
  u = Conjunction(Proofs([{0, 1}]), Proofs([{1, 2}]), theta)
  assert u == [(0, 1, 2)], u
  return 0


def TestProbabilityAgainstReference(trials=200):
  """The polynomial == reference TkpProbability."""
  rng = random.Random(11)
  failures = 0
  for trial in range(trials):
    n = rng.randint(2, 8)
    theta = [rng.uniform(0.05, 0.95) for _ in range(n)]
    proofs = RandomProofs(rng, n, rng.randint(1, 6))
    reference = tkp.TkpTop(ReferenceValue(proofs, theta), 6)
    ours = Probability(ReferenceAsLists(reference), theta)
    if abs(ours - tkp.TkpProbability(reference)) > 1e-9:
      failures += 1
      print('PROBABILITY MISMATCH', trial, ours)
  return failures


def TestGradientCentralDifference(trials=100):
  """The explicit polynomial gradient == central differences."""
  rng = random.Random(19)
  failures = 0
  for trial in range(trials):
    n = rng.randint(2, 7)
    theta = [rng.uniform(0.05, 0.95) for _ in range(n)]
    proofs = Canonicalize(
        Proofs(RandomProofs(rng, n, rng.randint(1, 5))), theta,
        rng.randint(1, 4))
    cotangent = rng.uniform(0.5, 2.0)
    gradient = [0.0] * n
    Gradient(proofs, theta, cotangent, gradient)
    for fact in range(n):
      epsilon = 1e-6
      up = list(theta)
      up[fact] += epsilon
      down = list(theta)
      down[fact] -= epsilon
      numeric = cotangent * (
          Probability(proofs, up) - Probability(proofs, down)) / (
              2 * epsilon)
      if abs(gradient[fact] - numeric) > 1e-6:
        failures += 1
        print('GRADIENT MISMATCH', trial, fact, gradient[fact], numeric)
  return failures


def TestTieBreakMinimal():
  """Miss Vi's minimal tie-break regression (2026-08-10).

  {0,4} takes the first slot at .4; {0,2} and {1,3} tie at .3 for the
  second. The canonical order keeps {0,2}: P = .46; a reversed order
  once kept the disjoint {1,3}: P = .58 — a tie-break is not harmless,
  it changes truncation, hence the probability."""
  theta = [.5, .5, .6, .6, .8]
  kept = Canonicalize(Proofs([{0, 4}, {0, 2}, {1, 3}]), theta, 2)
  assert kept == [(0, 4), (0, 2)], kept
  probability = Probability(kept, theta)
  assert abs(probability - 0.46) < 1e-9, probability
  return 0


def TestTruncationLossContract():
  """The documented approximation contract of losses on truncated DNF.

  A CONTRACT, not a failure: the probability is exact over the STORED
  proofs, so a positive loss is conservative and a negative loss is
  optimistic — 100 single-fact proofs of 0.1 at k=1 store P = .1,
  while the full space holds 1 - .9^100."""
  import math
  n = 100
  theta = [0.1] * n
  kept = Canonicalize(Proofs([{i} for i in range(n)]), theta, 1)
  p_stored = Probability(kept, theta)
  assert abs(p_stored - 0.1) < 1e-12, p_stored
  p_full = 1.0 - 0.9 ** n
  assert -math.log(p_stored) >= -math.log(p_full)          # Conservative.
  assert -math.log(1 - p_stored) <= -math.log(1 - p_full)  # Optimistic.
  assert -math.log(1 - p_full) / -math.log(1 - p_stored) > 100
  return 0


def TestWhackTheTop():
  """Negative training on truncated DNF suppresses routes one by one."""
  n = 5
  theta = [0.5] * n
  pools = Proofs([{i} for i in range(n)])

  def Step(theta):
    (kept,) = Canonicalize(pools, theta, 1)
    (fact,) = kept
    updated = list(theta)
    updated[fact] -= 0.1 * 1.0 / (1.0 - theta[fact])
    return updated

  for unused_step in range(3):
    theta = Step(theta)
  assert sum(1 for t in theta if t == 0.5) == n - 3, theta
  for unused_step in range(40):
    theta = Step(theta)
  assert all(t < 0.4 for t in theta), theta
  return 0


def TestThetaDependentHorizon():
  """Miss Vi's k=1 counterexample: the horizon depends on theta.

  A star of direct edges over a chain: under star-friendly theta the
  linear recursion stabilizes in a couple of sweeps; under chain-
  friendly theta the best proof of the far vertex takes 9 sweeps to
  build. A frozen short horizon reports the wrong proof silently —
  hence the executor iterates to the TRUE fixpoint and treats
  @Recursive as a loud correctness bound."""
  chain, direct = 9, 8   # c_i: v_i->v_{i+1} (0..8); d_i: v0->v_i (2..9).
  n = chain + direct

  def RunSweeps(theta, count):
    reach = {v: [] for v in range(1, 10)}
    stable_at = None
    for sweep in range(1, count + 1):
      new_reach = {}
      for v in range(1, 10):
        pool = list(reach[v])
        pool = []
        if v == 1:
          pool.append((0,))
        if v >= 2:
          pool.append((9 + v - 2,))
          pool.extend(Conjunction(reach[v - 1], [(v - 1,)], theta))
        new_reach[v] = Canonicalize(pool, theta, 1)
      if stable_at is None and new_reach == reach:
        stable_at = sweep
      reach = new_reach
    return reach, stable_at

  star = [0.4] * chain + [0.9] * direct
  unused_reach, stable_at = RunSweeps(star, 12)
  assert stable_at is not None and stable_at <= 4, stable_at
  frozen = stable_at + 2

  chainy = [0.95] * chain + [0.05] * direct
  truncated, unused = RunSweeps(chainy, frozen)
  full, full_stable = RunSweeps(chainy, 12)
  assert full_stable is not None, full_stable
  assert truncated[9] == [(16,)], truncated[9]
  assert full[9] == [tuple(range(9))], full[9]
  p_full = Probability(full[9], chainy)
  assert abs(p_full - 0.95 ** 9) < 1e-9, p_full
  return 0


def TestSparseScale():
  """The 5x5 grid world costs kilobytes of symbols, not gigabytes.

  The all-pairs doubling recursion of the once-Colab-crashing 5x5
  program: canonicalizing every pool is plain python over a few
  thousand proofs; tracemalloc guards that no dense representation
  sneaks back."""
  import tracemalloc
  rng = random.Random(17)
  n = 40
  theta = [rng.uniform(0.3, 0.9) for _ in range(n)]
  tracemalloc.start()
  total = 0
  for unused_cell in range(625):
    pool = Proofs(RandomProofs(rng, n, 20))
    kept = Canonicalize(pool, theta, 4)
    total += len(kept)
  unused_current, peak = tracemalloc.get_traced_memory()
  tracemalloc.stop()
  assert total, total
  assert peak < 4 * 1024 * 1024, peak
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
  failures += TestCanonicalizeAgainstReference()
  failures += TestTiesAgainstReference()
  failures += TestAbsorption()
  failures += TestConjunction()
  failures += TestProbabilityAgainstReference()
  failures += TestGradientCentralDifference()
  failures += TestTieBreakMinimal()
  failures += TestTruncationLossContract()
  failures += TestWhackTheTop()
  failures += TestThetaDependentHorizon()
  failures += TestSparseScale()
  failures += TestGuardsRefused()
  failures += TestRepeatedVariablesRefused()
  failures += TestNonPositiveKRefused()
  failures += TestCanonicalFieldOrder()
  failures += TestThetaSupportChecked()
  failures += TestIsFunctionalUncompilable()
  print('tkp_tensor_test: failures: %d' % failures)
  return 1 if failures else 0


if __name__ == '__main__':
  sys.exit(main())
