# Functors for finding paths in a *directed* graph.

# Works for ~256 steps.
# Using this length to the full extent is barely practical, as the number of
# elements in the relation is at least quadratic of the length of the longest path.

# Only going along the edges is allowed.
# Note that by this definition a vertex is not necessarily reachable from
# itself. It is reachable only if there is a loop and distance is never
# zero.
# If you need to define distance with any vertex being distance zero from
# each other then apply this functor and create a new predicate, overriding
# self distance.

####################
# Distance functor.

# With recursion distance in G would be defined as follows:
# GraphDistance(a, b) Min= G(a, b);
# GraphDistance(a, c) Min= GraphDistance(a, b) + GraphDistance(b, c);

# Without recursion in the language we have to unfold recursion into a
# series of non-recursive steps.
# D<N> is running O(2^N) SQL querries and is capturing chains of the
# lenght up to 2^(2^(N - 1)).

D0(a, b) Min= 1 :- G(a, b);

@Ground(D1);
D1(a, b) Min= D0(a, b);
D1(a, c) Min= D0(a, b) + D0(b, c);

D2 := D1(D0: D1);
D3 := D2(D0: D2);
D4 := D3(D0: D3);

GraphDistance := D4();

#########################
# Graph path functor.
# This functor finds distance, as well as the shortest path between
# any two vertices.

GP0(a, b) ArgMin= {distance: 1, path: [{source: a, target: b}]} -> 1 :-
  G(a, b);

@Ground(GP1);
GP1(a, b) ArgMin= gp -> d :-
  gp == GP0(a, b), d == gp.distance;

GP1(a, c) ArgMin= {distance: d1 + d2,
                   path: ArrayConcat(path1, path2)} -> (d1 + d2):-
  GP0(a, b) == gp_ab,
  GP0(b, c) == gp_bc,
  d1 == gp_ab.distance,
  path1 == gp_ab.path,
  d2 == gp_bc.distance,
  path2 == gp_bc.path;

GP2 := GP1(GP0: GP1);
GP3 := GP2(GP0: GP2);
GP4 := GP3(GP0: GP3);

GraphPath := GP4();
