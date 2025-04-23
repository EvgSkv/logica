# Finding set of nodes connected to a start node.
# Start node is considered connected to itself.
C(x) :- StartNode(x);
# A node connected to a connected node is connected.
C(y) :- C(x), E(x, y);
