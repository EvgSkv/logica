@Ground(G);
G(a, b) :- `("g1k.csv")`(a, b);

@Recursive(TC, ∞, stop: Stop);
TC(a, b) distinct :- G(a, b);
TC(a, c) distinct :- TC(a, b), G(b, c);

OldN() += 1 :- TC();
Stop() :- OldN() == Sum{1 :- TC()};

N() += 1 :- TC(a, b);
