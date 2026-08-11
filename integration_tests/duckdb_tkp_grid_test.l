# The 5x5 grid world: the memory regression of the sparse TKP kernel.
#
# This very configuration (625 key cells, a doubling composition pool
# of 25 * 4^2 + 1 candidates) once materialized a pairwise-subset
# tensor of 160 GB and crashed the machine; the greedy canonicalization
# keeps it in hundreds of MB. Positive and negative supervision over a
# monotone grid: the MustHave corner rises, the MustHaveNot corner
# falls. The sparse symbolic executor runs it in a second within
# hundreds of MB.

import examples.extensions.tkp.MakeFact;
import examples.extensions.tkp.ProbConjunction;
import examples.extensions.tkp.TKP;
import examples.extensions.tkp.TkpProbability;

@Engine("duckdb", tensor_engine: "numpy");

NodeName(i, j) = "node_" ++ ToString(i) ++ "-" ++ ToString(j);

G(a, b) :-
  n = 5,
  i in Range(n),
  j in Range(n),
  a == NodeName(i, j),
  (t_i = i + 1, t_j = j | t_i = i, t_j = j + 1),
  b = NodeName(t_i, t_j),
  t_i < n,
  t_j < n;

W(a, b) = 0.5 :- G(a, b);

MustHave("node_0-0", "node_1-4");
MustHaveNot("node_0-0", "node_4-1");

EdgeProb(a, b) = 1.0 / (1.0 + Exp(-W(a, b))) :- G(a, b);

Edge(a, b) = MakeFact(predicate: "Edge", args: [a, b],
                      probability: EdgeProb(a, b)) :- G(a, b);

T4P(x) = TKP(x, 4);

@Recursive(Path, 10);
Path(x, y) T4P= Edge(x, y);
Path(x, z) T4P= ProbConjunction(Path(x, y), Path(y, z));

Loss() += -Log(TkpProbability(Path(x, y)) + 0.000000001) :- MustHave(x, y);
# The negative loss sees only the STORED top-k DNF: dropped proofs go
# unpenalized (optimistic), while the positive loss is conservative.
Loss() += -Log(1.0 - TkpProbability(Path(x, y)) + 0.000000001) :- MustHaveNot(x, y);

@NeuralTarget(Loss, learn: [W], steps: 30, learning_rate: 0.3);

@OrderBy(Report, "col0");
Report(y, p: Round(TkpProbability(Path("node_0-0", y)), 4)) :- Path("node_0-0", y);

# The probability of the ATOM itself: the same inclusion-exclusion
# polynomial over a one-proof, one-fact DNF — numerically its theta.
@OrderBy(Edges, "col0", "col1");
Edges(a, b, p: Round(TkpProbability(Edge(a, b)), 4)) :- G(a, b);
