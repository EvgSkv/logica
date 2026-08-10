#!/usr/bin/python
"""TKP — top-k proofs: probabilistic DNFs for duckdb.

A value is a list of proofs; a proof is a list of facts; a fact is
{predicate, args, probability}. The parity decisions: exact
inclusion-exclusion; ranking by probability with lexicographic ties;
dedup and absorption; truncation to k happens only in TkpTop.

MakeFact and TKP are defined on the Logica side:
  MakeFact(predicate:, args:, probability:) = [{facts: [{...}]}];
  TKP(x, k) = TkpTop(MergeList(x), k);
"""

LOGICA_EXTENSION = {
  "aggregations": [],
  "functions": ["TkpProbConjunction", "TkpTop", "TkpProbability"],
  "logica": """
TkpArgsString(args) = v :-
  v == SqlExpr("to_json({a})::varchar", {a: args}), v ~ Str;
TkpMakeFact(predicate:, args:, probability:) =
  [{facts: [{predicate:, args: TkpArgsString(args), probability:}]}];
TKP(x, k) = TkpTop(MergeList(x), k);

# Convenient synonyms; the neural layer protocol is Tkp-names only.
MakeFact(predicate:, args:, probability:) =
  TkpMakeFact(predicate:, args:, probability:);
ProbConjunction(a, b) = TkpProbConjunction(a, b);
"""
}


class Fact:
  predicate: str
  args: str
  probability: float


class Proof:
  facts: list[Fact]


def NewProof(facts: list[Fact]) -> Proof:
  p = Proof()
  p.facts = facts
  return p


def FactIdentity(f: Fact) -> str:
  return f.predicate + "(" + f.args + ")"


def ProofIdentity(pr: Proof) -> str:
  result: str = ""
  i: int = 0
  while i < len(pr.facts):
    result = result + FactIdentity(pr.facts[i]) + ";"
    i = i + 1
  return result


def ProofProbability(pr: Proof) -> float:
  result: float = 1.0
  i: int = 0
  while i < len(pr.facts):
    result = result * pr.facts[i].probability
    i = i + 1
  return result


def DedupFacts(facts: list[Fact]) -> list[Fact]:
  ordered = sorted(facts, key=lambda f: FactIdentity(f))
  result: list[Fact] = []
  i: int = 0
  while i < len(ordered):
    if i == 0 or FactIdentity(ordered[i]) != FactIdentity(ordered[i - 1]):
      result.append(ordered[i])
    i = i + 1
  return result


def IsSubsetOf(pa: Proof, pb: Proof) -> bool:
  i: int = 0
  j: int = 0
  while i < len(pa.facts):
    if j == len(pb.facts):
      return False
    ai = FactIdentity(pa.facts[i])
    bj = FactIdentity(pb.facts[j])
    if ai == bj:
      i = i + 1
      j = j + 1
    elif bj < ai:
      j = j + 1
    else:
      return False
  return True


def Canonicalize(proofs: list[Proof], k: int) -> list[Proof]:
  """Dedup, absorption, order (probability desc, lex), top-k.

  k < 0 means no truncation."""
  # Two stable sorts = (probability desc, lexicographic ties).
  ordered = sorted(proofs, key=lambda p: ProofIdentity(p))
  ordered = sorted(ordered, key=lambda p: -ProofProbability(p))
  result: list[Proof] = []
  i: int = 0
  while i < len(ordered):
    keep: bool = True
    j: int = 0
    while j < len(result):
      if IsSubsetOf(result[j], ordered[i]):
        keep = False  # a duplicate, or absorbed by a likelier proof
      j = j + 1
    if keep:
      result.append(ordered[i])
      if k >= 0 and len(result) == k:
        return result
    i = i + 1
  return result


def TkpProbConjunction(a: list[Proof],
                       b: list[Proof]) -> list[Proof]:
  proofs: list[Proof] = []
  i: int = 0
  while i < len(a):
    j: int = 0
    while j < len(b):
      proofs.append(NewProof(DedupFacts(a[i].facts + b[j].facts)))
      j = j + 1
    i = i + 1
  return Canonicalize(proofs, -1)


def TkpTop(proofs: list[Proof], k: int) -> list[Proof]:
  return Canonicalize(proofs, k)


def TkpProbability(v: list[Proof]) -> float:
  """Exact inclusion-exclusion over the STORED proofs.

  This is the probability of the top-k object itself, not of the full
  proof space: proofs dropped by truncation contribute nothing. Since
  dropping proofs can only lower the probability, on a truncated DNF a
  positive loss -log(P) is conservative (over-penalizes), while a
  negative loss -log(1-P) is optimistic — it does not penalize the
  dropped proofs at all, and a large mass of individually weak proofs
  can hide below the cut. When negative supervision matters, raise k
  and check the sensitivity of the result to k."""
  n: int = len(v)
  count: int = 1
  i: int = 0
  while i < n:
    count = count * 2
    i = i + 1
  total: float = 0.0
  subset: int = 1
  while subset < count:
    merged: list[Fact] = []
    size: int = 0
    bit: int = 1
    p: int = 0
    while p < n:
      if (subset // bit) % 2 == 1:
        merged = merged + v[p].facts
        size = size + 1
      bit = bit * 2
      p = p + 1
    sign: float = 1.0 if size % 2 == 1 else -1.0
    total = total + sign * ProofProbability(NewProof(DedupFacts(merged)))
    subset = subset + 1
  return total
