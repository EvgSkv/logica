# Small cycle recursion test.
@Engine("sqlite");
A(x) distinct :- B(x);
B(x) :- C(x);
C(x) :- x == 0 | A(x);
Test(x) :- A(x);