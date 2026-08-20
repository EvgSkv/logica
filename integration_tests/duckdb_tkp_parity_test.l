# The N-unfoldings parity twin, SQL side. A 4-chain with a shortcut,
# @Recursive(Path, 2): two unfoldings do NOT reach the fixpoint (the
# full chain path needs a third), so the report pins the exact
# unfolding-count semantics. The neural twin shares this golden.

import examples.extensions.tkp.MakeFact;
import examples.extensions.tkp.ProbConjunction;
import examples.extensions.tkp.TKP;
import examples.extensions.tkp.TkpProbability;

@Engine("duckdb");

E("a", "b", 0.9); E("b", "c", 0.8); E("c", "d", 0.7);
E("d", "e", 0.6); E("a", "c", 0.5);

EdgeProb(x, y) = p :- E(x, y, p);
Edge(x, y) = MakeFact(predicate: "e", args: [x, y],
                      probability: EdgeProb(x, y)) :- E(x, y, p);

T2P(x) = TKP(x, 2);

@Recursive(Path, 2);
Path(x, y) T2P= Edge(x, y);
Path(x, z) T2P= ProbConjunction(Path(x, y), Path(y, z));

@OrderBy(Report, "col0", "col1");
Report(x, y, p: Round(TkpProbability(Path(x, y)), 4)) :- Path(x, y);
