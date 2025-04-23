# Rule 1: Distance from the Start node is 0.
D(Start()) Min= 0;
# Rule 2: Triangle inequality.
D(y) Min= D(x) + 1 :- E(x,y);
