# Testing subscript of implication optimization.

@Engine("bigquery");

Test(n, a, b, c) :-
  n in Range(10),
  r == (
    if n < 5 then {
      a: 1,
      b: 2
    } else if n < 7 then {
      a: 3,
      b: 4
    } else {
      a: 5,
      b: 6
    }
  ),
  a == r.a,
  b == r.b,
  i in [{c: 11}, {c: 12}],
  c == (
    if n < 5 then {
      c: 10
    } else i
  ).c;
