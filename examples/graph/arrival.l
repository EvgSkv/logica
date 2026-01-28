# Rule 1: Starting condition.
Arrival(Start()) Min= 0;
# Rule 2: Traversal of an edge when edge exists.
Arrival(y) Min= Greatest(Arrival(x),t0) :-
  E(x,y,t0,t1), Arrival(x) <= t1;