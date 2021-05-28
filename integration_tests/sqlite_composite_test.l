# Testing composite types in SQLite.

@Engine("sqlite");

Test(
    r:,
    r_sq:,
    r_sq_l:,
    records:) :-
  r == Range(5),
  r_sq List= (x * x :- x in r),
  r_sq_l List= (x :- x in r_sq, x > 5),
  records == [{a: 1, b: "one"}, {a: 2, b: "two"}]; 