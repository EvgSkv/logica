# Tests for reachability.l library.
# Mechanically only testing ZeroConnects, other predicates are for
# manual inspection.

import lib.reachability.GraphPath;
import lib.reachability.GP3;
import lib.reachability.GraphDistance;

D(a, a + 1) :- a in Range(100);

@OrderBy(P, "col0", "col1");
P := GraphPath(G: D);

@OrderBy(PathTo99, "col0", "col1");
PathTo99(source, target) :-
  p == P(0, 99),
  e in p.path,
  source == e.source,
  target == e.target;

PartialPath := GP3(G: D);

PartialDistance := GraphDistance(G: D);

@OrderBy(ZeroConnects, "col0");
ZeroConnects(x, x, d) :-
  PartialPath(0, x),
  d == PartialDistance(0, x);

Test(x) :- ZeroConnects(x);