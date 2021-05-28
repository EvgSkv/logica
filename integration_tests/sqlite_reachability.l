# Testing recursive path finding in SQLite.

@Engine("sqlite");

G(1, 2);
G(2, 3);
G(3, 4);
G(3, 5);
G(1, 8);

C(a, b) distinct :- G(a, b) | G(b, a);

Path(source:, target:, length? Min= 1, path? ArgMin= ([source] -> 1)) distinct :-
  C(source, target);

Path(source: a, target: c,
     length? Min= l1 + l2,
     path? ArgMin= ArrayConcat(p1, p2) -> (l1 + l2)) distinct :-
  Path(source: a, target: b, length: l1, path: p1),
  Path(source: b, target: c, length: l2, path: p2);

FinalPath(source:, target:, final_path:) :-
  Path(source:, target:, path:),
  final_path == ArrayConcat(path, [target]),
  source != target;

Test := FinalPath();
