@Engine("duckdb", threads: 2);

# Regression: nested functional helpers must not be auto-grounded, and
# the multi-body aggregate must retain the path -> Size(path) transform.
s(x) = ToString(x);
G(a, b) :-
  m = 2 * n,
  n = 10,
  a = NaturalHash("a-" ++ s(i)) % n,
  b = NaturalHash("b-" ++ s(i)) % n,
  i in Range(m);

Shortest(p) = ArgMin(p -> Size(p));
@Recursive(Path, mode: "socratic");
Path(a, b) Shortest= [a] :- G(a, b);
Path(a, c) Shortest= Path(a, b) ++ Path(b, c);
