# Transitive closure functor.
# Works for ~256 steps.
# Using this length to the full extent is barely practical, as the number of
# elements in the relation is at least quadratic of the length of the longest path.

# With recursion transitive closure of predicate R is defined as follows:
# TransitiveClosure(a, b) distinct :- R(a, b);
# TransitiveClosure(a, c) distinct :-
#   TransitiveClosure(a, b),
#   TransitiveClosure(b, c);

# Without recursion in the language we have to unfold recursion into a
# series of non-recursive steps.
# TC<N> is running O(2^N) SQL querries and is capturing chains of the
# length up to 2^(2^(N - 1)).


TC0(a, b) distinct :- R(a, b);

@Ground(TC1);
TC1(a, b) distinct :- TC0(a, b);
TC1(a, c) distinct :- TC0(a, b), TC0(b, c);

TC2 := TC1(TC0: TC1);
TC3 := TC2(TC0: TC2);
TC4 := TC3(TC0: TC3);

TransitiveClosure := TC4();

