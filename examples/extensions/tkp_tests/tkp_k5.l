import examples.extensions.tkp.MakeFact;
import examples.extensions.tkp.ProbConjunction;
import examples.extensions.tkp.TKP;
import examples.extensions.tkp.TkpProbability;

@Engine("duckdb", tensor_engine: "jax");

V(v) :- v in ["v1", "v2", "v3", "v4", "v5"];
PotentialEdge(a, b) distinct :- V(a), V(b), a != b;

MustHave("v1", "v2");
MustHaveNot("v1", "v3");

W(a, b) = 0.0 :- PotentialEdge(a, b);
EdgeProb(a, b) = 1.0 / (1.0 + Exp(-W(a, b))) :- PotentialEdge(a, b);

Edge(a, b) = MakeFact(predicate: "Edge", args: [a, b],
                      probability: EdgeProb(a, b)) :- PotentialEdge(a, b);

T4P(x) = TKP(x, 4);

@Recursive(Path, 12);
Path(x, y) T4P= Edge(x, y);
Path(x, z) T4P= ProbConjunction(Path(x, y), Path(y, z));

Loss() += -Log(TkpProbability(Path(x, y)) + 0.000000001) :- MustHave(x, y);
# The negative loss sees only the STORED top-k DNF: dropped
# proofs go unpenalized (optimistic), while the positive loss
# is conservative. When negative supervision matters, raise k
# and check the sensitivity of the result to k.
Loss() += -Log(1.0 - TkpProbability(Path(x, y)) + 0.000000001) :- MustHaveNot(x, y);

@OrderBy(PathShow, "col0", "col1");
PathShow(x, y) = TkpProbability(Path(x, y));

@NeuralTarget(Loss, learn: [W], steps: 500, learning_rate: 0.3);

@OrderBy(Report, "col0");
Report(y, p: Round(TkpProbability(Path("v1", y)), 4)) :- Path("v1", y);

@OrderBy(Edges, "col0", "col1");
Edges(a, b, p: Round(EdgeProb(a, b), 3)) :- PotentialEdge(a, b);
