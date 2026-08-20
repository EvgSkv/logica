# The N-unfoldings parity twin, NEURAL side: the same universe with
# theta through a zero-step @NeuralTarget — the sparse solver runs the
# probes and the write-back, the report must match the SQL twin's
# golden BYTE FOR BYTE (this file has no golden of its own).

import examples.extensions.tkp.MakeFact;
import examples.extensions.tkp.ProbConjunction;
import examples.extensions.tkp.TKP;
import examples.extensions.tkp.TkpProbability;

@Engine("duckdb", tensor_engine: "numpy");

E("a", "b", 0.9); E("b", "c", 0.8); E("c", "d", 0.7);
E("d", "e", 0.6); E("a", "c", 0.5);

W(x, y) = Log(p / (1.0 - p)) :- E(x, y, p);
EdgeProb(x, y) = 1.0 / (1.0 + Exp(-W(x, y))) :- E(x, y, p);
Edge(x, y) = MakeFact(predicate: "e", args: [x, y],
                      probability: EdgeProb(x, y)) :- E(x, y, p);

T2P(x) = TKP(x, 2);

@Recursive(Path, 2);
Path(x, y) T2P= Edge(x, y);
Path(x, z) T2P= ProbConjunction(Path(x, y), Path(y, z));

Loss() += 0.0 * TkpProbability(Path(x, y)) :- E(x, y, p);
@NeuralTarget(Loss, learn: [W], steps: 0, learning_rate: 0.1);

@OrderBy(Report, "col0", "col1");
Report(x, y, p: Round(TkpProbability(Path(x, y)), 4)) :- Path(x, y);
