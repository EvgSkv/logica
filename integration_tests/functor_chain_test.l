# Verifying functor call for a chain.

A(0);
B(x) :- A(x);
C(x) :- B(x);
D(x) :- C(x);
E(x) :- D(x);
F(a:, e:) :- A(a), E(e);

A1(1);
C2(2);
F12 := F(A: A1, C: C2);

Test(..r) :- F12(..r);
