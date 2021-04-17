# Examples of using TransitiveClosure functor.

# Importing the closure functor.
import lib.closure.TransitiveClosure;

# Importing RandomGraph functor and its artuments to use in an
# example.
import lib.random.RandomGraph;
import lib.random.RandomGraphNodeCount;
import lib.random.RandomGraphEdgeCount;

# Importing royal parent predicate to use in an example.
import examples.scripts.queen_victoria.Parent as RoyalParent;


##################################################
# Transitively closing a random directed graph.

NodeCount() = 10;
EdgeCount() = 10;

DirectedGraph := RandomGraph(RandomGraphNodeCount: NodeCount,
                             RandomGraphEdgeCount: EdgeCount);

@OrderBy(ClosedGraph, "col0", "col1");
ClosedGraph := TransitiveClosure(R: DirectedGraph);

GreaterThan(x) List= y :- ClosedGraph(x, y);

##################################################################
# Finding descendants of each of the member of the royal family.

RoyalAncestor := TransitiveClosure(R: RoyalParent);

@OrderBy(DescendantsOf, "col0");
DescendantsOf(ancestor: x, descendants? Array= y -> y) distinct :-
  RoyalAncestor(x, y);
