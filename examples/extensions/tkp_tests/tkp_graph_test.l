# A TKP graph task: the SQL part, forward only, no learning.
import examples.extensions.tkp.MakeFact;
import examples.extensions.tkp.ProbConjunction;
import examples.extensions.tkp.TKP;
import examples.extensions.tkp.TkpProbability;

T3P(x) = TKP(x, 3);

# --- data ---
PotentialEdge("a", "b"); PotentialEdge("b", "c");
PotentialEdge("a", "c"); PotentialEdge("c", "d"); PotentialEdge("b", "d");
EdgeProb(a, b) = 0.5 :- PotentialEdge(a, b);

Edge(a, b) = MakeFact(predicate: "Edge", args: [a, b],
                      probability: EdgeProb(a, b)) :- PotentialEdge(a, b);

@Recursive(Path, 8);
Path(x, y) T3P= Edge(x, y);
Path(x, z) T3P= ProbConjunction(Path(x, y), Path(y, z));

@OrderBy(Report, "col0", "col1");
Report(x, y, p: Round(TkpProbability(Path(x, y)), 4)) :- Path(x, y);
