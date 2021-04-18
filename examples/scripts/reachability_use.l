# Using GraphPath functor to find paths in graphs.
# Predicates to run: MyGraphPath, TheLine.

import lib.reachability.GraphPath;

# Importing RandomGraph functor and its artuments to use in an
# example.
import lib.random.RandomGraph;
import lib.random.RandomGraphNodeCount;
import lib.random.RandomGraphEdgeCount;

import examples.scripts.queen_victoria.Parent;

# Finding paths in a random graph.

NodeCount() = 10;
EdgeCount() = 10;

DirectedGraph := RandomGraph(RandomGraphNodeCount: NodeCount,
                             RandomGraphEdgeCount: EdgeCount);

@OrderBy(MyGraphPath, "col0", "col1");
MyGraphPath := GraphPath(G: DirectedGraph);

# Finding descendancy line from Queen Victoria to Prince Charles.

RoyalLine := GraphPath(G: Parent);

TheLine() = RoyalLine("Queen Victoria",
                      "Prince Charles");