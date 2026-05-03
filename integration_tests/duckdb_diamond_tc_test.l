
@Engine("duckdb");

s(x) = ToString(x);

@Ground(G);
G(a, b) :-
  i in Range(1000),
  a == NaturalHash("a" ++ s(i)) % 100,
  b == NaturalHash("b" ++ s(i)) % 100,
  a ~ Num, b ~ Num;

@Recursive(TC, 1000, stop: Stop);
TC(x:a, y:b) distinct :- G(a, b);
TC(x:a, y:c) distinct :- TC(x:a, y:b), G(b, c);

PrevTC() Array= r -> r :- TC(..r), r ~ {x: Num, y: Num};
Stop() :- Array{ r -> r :- TC(..r) } == PrevTC();

Test() Max= 1 :- TC(x:, y:);
