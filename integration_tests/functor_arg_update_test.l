@Engine("sqlite");
A("a");
B("b");
Z1("z1");
Z2("z2");
C(x) :- A(x) | B(x);

E(x) :- D(x);

D := C(A: Z1);

F := E(B: Z2);

Test := F();