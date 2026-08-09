# Графовая задача на TKP: SQL-часть, форвард без обучения.
import tkp.ProbConjunction;
import tkp.TkpTop;
import tkp.TkpProbability;

@Engine("duckdb");

MakeFact(predicate:, args:, probability:) =
  [{facts: [{predicate:, args: ArgsString(args), probability:}]}];
ArgsString(args) = v :-
  v == SqlExpr("array_to_string({a}, '|')", {a: args}), v ~ Str;

TKP(x, k) = TkpTop(MergeList(x), k);
T3P(x) = TKP(x, 3);

# --- данные ---
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
