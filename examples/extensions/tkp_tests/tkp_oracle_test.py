"""Oracle: inclusion-exclusion vs world enumeration; determinism."""
import itertools, random
import tkp

def MakeFact(predicate, args, probability):
  f = tkp.Fact()
  f.predicate = predicate
  f.args = args
  f.probability = probability
  return [tkp.NewProof([f])]


def WorldProbability(proofs_facts, fact_probs, satisfied_fn):
  total = 0.0
  facts = sorted(fact_probs)
  for world in itertools.product([0, 1], repeat=len(facts)):
    w = dict(zip(facts, world))
    pw = 1.0
    for f, bit in w.items():
      pw *= fact_probs[f] if bit else 1 - fact_probs[f]
    if satisfied_fn(w):
      total += pw
  return total


def RandomExpression(rng, facts, depth):
  if depth == 0 or rng.random() < 0.3:
    f = rng.choice(facts)
    return ('fact', f)
  if rng.random() < 0.5:
    return ('and', RandomExpression(rng, facts, depth - 1),
            RandomExpression(rng, facts, depth - 1))
  return ('or', [RandomExpression(rng, facts, depth - 1)
                 for _ in range(rng.randint(2, 3))])


def Evaluate(expr, fact_probs, k):
  kind = expr[0]
  if kind == 'fact':
    return MakeFact('F', expr[1], fact_probs[expr[1]])
  if kind == 'and':
    return tkp.TkpProbConjunction(Evaluate(expr[1], fact_probs, k),
                               Evaluate(expr[2], fact_probs, k))
  return tkp.TkpTop(sum([Evaluate(e, fact_probs, k) for e in expr[1]], []), k)


def Satisfies(expr, world):
  kind = expr[0]
  if kind == 'fact':
    return world[expr[1]] == 1
  if kind == 'and':
    return Satisfies(expr[1], world) and Satisfies(expr[2], world)
  return any(Satisfies(e, world) for e in expr[1])


def ObjectSatisfies(value, world):
  return any(all(world[f.args] == 1 for f in p.facts) for p in value)


rng = random.Random(11)
failures = 0
for trial in range(200):
  facts = [chr(ord('a') + i) for i in range(rng.randint(2, 6))]
  fact_probs = {f: round(rng.uniform(0.1, 0.9), 3) for f in facts}
  expr = RandomExpression(rng, facts, 3)

  # 1. No truncation: object probability == formula probability.
  v = Evaluate(expr, fact_probs, 999)
  exact = WorldProbability(None, fact_probs, lambda w: Satisfies(expr, w))
  got = tkp.TkpProbability(v)
  if abs(got - exact) > 1e-9:
    failures += 1
    print('EXACT MISMATCH', trial, got, exact, expr)

  # 2. Truncated to k=2: object probability == STORED DNF probability.
  v2 = Evaluate(expr, fact_probs, 2)
  stored = WorldProbability(None, fact_probs,
                            lambda w: ObjectSatisfies(v2, w))
  got2 = tkp.TkpProbability(v2)
  if abs(got2 - stored) > 1e-9:
    failures += 1
    print('TRUNCATED MISMATCH', trial, got2, stored)

  # 3. Determinism: shuffled construction order, same canonical form.
  def Shuffle(e):
    if e[0] == 'or':
      children = [Shuffle(c) for c in e[1]]
      rng.shuffle(children)
      return ('or', children)
    if e[0] == 'and':
      a, b = Shuffle(e[1]), Shuffle(e[2])
      return ('and', b, a) if rng.random() < 0.5 else ('and', a, b)
    return e
  v3 = Evaluate(Shuffle(expr), fact_probs, 2)
  id2 = [tkp.ProofIdentity(p) for p in v2]
  id3 = [tkp.ProofIdentity(p) for p in v3]
  if id2 != id3:
    failures += 1
    print('DETERMINISM MISMATCH', trial, id2, id3)

print('tkp_test: 200 trials x 3 checks, failures:', failures)
