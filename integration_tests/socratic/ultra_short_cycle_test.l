# Testing very short recursive cycles.
@Engine("duckdb");
@Recursive(Q, 8, mode: "socratic");
@Recursive(F, 8, mode: "socratic");

Q(x) :- x == 1 | Q(x);

F(x) = F(x) + 1;
F(0) = 0;

Test("F", x, F(x));
Test("Q", -1, q) :- Q(q);
