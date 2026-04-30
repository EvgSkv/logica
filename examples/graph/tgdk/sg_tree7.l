G(a, b) :- `("tree7.csv")`(a, b);

@Recursive(SG, -1, stop: Done);
SG(x, y) distinct :- G(a, x), G(a, y);
SG(x, y) distinct :- SG(a, b), G(a, x), G(b, y);
PrevSG(x, y) :- SG(x, y);
Done() :- Sum{ 1 :- SG(x, y) } == Sum{ 1 :- PrevSG(x, y) };

N() += 1 :- SG(x, y);
