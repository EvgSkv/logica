# Rule 1: Transitive closure base case.
TC(x,y) distinct :- E(x,y);
# Rule 2: Transitive closure inductive step.
TC(x,y) distinct :- TC(x,z), TC(z,y);
# Rule 3: Transitive reduction.
TR(x,y) :- E(x,y), ~(E(x,z), TC(z,y));