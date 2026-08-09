#!/usr/bin/python
"""TKP — top-k proofs: вероятностные ДНФ для duckdb.

Значение — список доказательств; доказательство — список фактов;
факт — {predicate, args, probability}. Решения чётности:
включение-исключение; ранжировка по вероятности, ничьи лексикографски;
дедуп и поглощение; обрезка до k — только в TkpTop.

MakeFact и TKP определяются на стороне Logica:
  MakeFact(predicate:, args:, probability:) = [{facts: [{...}]}];
  TKP(x, k) = TkpTop(MergeList(x), k);
"""

LOGICA_EXTENSION = {
  "aggregations": [],
  "functions": ["ProbConjunction", "TkpTop", "TkpProbability"],
  "logica": """
ArgsString(args) = v :-
  v == SqlExpr("to_json({a})::varchar", {a: args}), v ~ Str;
MakeFact(predicate:, args:, probability:) =
  [{facts: [{predicate:, args: ArgsString(args), probability:}]}];
TKP(x, k) = TkpTop(MergeList(x), k);
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
  """Дедуп, поглощение, порядок (вероятность убыв., лекс.), топ-k.

  k < 0 — не обрезать."""
  # Два стабильных сорта = (вероятность убыв., ничьи лексикографски).
  ordered = sorted(proofs, key=lambda p: ProofIdentity(p))
  ordered = sorted(ordered, key=lambda p: -ProofProbability(p))
  result: list[Proof] = []
  i: int = 0
  while i < len(ordered):
    keep: bool = True
    j: int = 0
    while j < len(result):
      if IsSubsetOf(result[j], ordered[i]):
        keep = False  # дубликат или поглощение более вероятным
      j = j + 1
    if keep:
      result.append(ordered[i])
      if k >= 0 and len(result) == k:
        return result
    i = i + 1
  return result


def ProbConjunction(a: list[Proof],
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
  """Точное включение-исключение по доказательствам."""
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
