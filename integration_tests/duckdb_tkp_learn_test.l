import examples.extensions.tkp.MakeFact;
import examples.extensions.tkp.ProbConjunction;
import examples.extensions.tkp.TKP;
import examples.extensions.tkp.TkpProbability;

@Engine("duckdb", tensor_engine: "numpy");

PotentialEdge("a", "b"); PotentialEdge("b", "c");
PotentialEdge("a", "g"); PotentialEdge("g", "c");
PotentialEdge("c", "d"); PotentialEdge("d", "e");
PotentialEdge("c", "f"); PotentialEdge("f", "e");
MustHave("a", "e");
MustHaveNot("a", "f");

W(a, b) = 0.0 :- PotentialEdge(a, b);
EdgeProb(a, b) = 1.0 / (1.0 + Exp(-W(a, b))) :- PotentialEdge(a, b);

Edge(a, b) = MakeFact(predicate: "Edge", args: [a, b],
                      probability: EdgeProb(a, b)) :- PotentialEdge(a, b);

T4P(x) = TKP(x, 4);

# 12 sweeps: under the initial all-0.5 parameters the canonical
# (lexicographic) tie-break keeps admitting lexicographically earlier
# proofs of equal probability as longer paths appear, so the pool
# composition settles later than the graph diameter suggests.
@Recursive(Path, 12);
Path(x, y) T4P= Edge(x, y);
Path(x, z) T4P= ProbConjunction(Path(x, y), Path(y, z));

Loss() += -Log(TkpProbability(Path(x, y)) + 0.000000001) :- MustHave(x, y);
# The negative loss sees only the STORED top-k DNF: dropped
# proofs go unpenalized (optimistic), while the positive loss
# is conservative. When negative supervision matters, raise k
# and check the sensitivity of the result to k.
Loss() += -Log(1.0 - TkpProbability(Path(x, y)) + 0.000000001) :- MustHaveNot(x, y);

@NeuralTarget(Loss, learn: [W], steps: 300, learning_rate: 0.3);

@OrderBy(Report, "col0");
Report(y, p: Round(TkpProbability(Path("a", y)), 4)) :- Path("a", y);
