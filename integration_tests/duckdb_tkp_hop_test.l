# A STANDALONE (non-recursive) TKP disjunction: TwoHop is proof-valued
# but forms no recursion group — the executor sort that once fell
# through the cracks between atoms and recursive members. Learning
# must reach the edge weights through it, and the probability of the
# ATOM itself must publish alongside.

import examples.extensions.tkp.MakeFact;
import examples.extensions.tkp.ProbConjunction;
import examples.extensions.tkp.TKP;
import examples.extensions.tkp.TkpProbability;

@Engine("duckdb", tensor_engine: "numpy");

PotentialEdge("a", "b"); PotentialEdge("b", "c");
PotentialEdge("a", "x"); PotentialEdge("x", "c");
PotentialEdge("b", "d");

W(a, b) = 0.0 :- PotentialEdge(a, b);
EdgeProb(a, b) = 1.0 / (1.0 + Exp(-W(a, b))) :- PotentialEdge(a, b);

Edge(a, b) = MakeFact(predicate: "Edge", args: [a, b],
                      probability: EdgeProb(a, b)) :- PotentialEdge(a, b);

T2P(x) = TKP(x, 2);

TwoHop(a, c) T2P= ProbConjunction(Edge(a, b), Edge(b, c));

Loss() += -Log(TkpProbability(TwoHop(a, c)) + 0.000000001) :-
  a == "a", c == "c";
@NeuralTarget(Loss, learn: [W], steps: 200, learning_rate: 0.3);

@OrderBy(Report, "col0", "col1");
Report(a, c, p: Round(TkpProbability(TwoHop(a, c)), 4)) :- TwoHop(a, c);
