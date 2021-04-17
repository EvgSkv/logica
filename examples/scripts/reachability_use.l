
import lib.reachability.GraphPath;

# Importing RandomGraph functor and its artuments to use in an
# example.
import lib.random.RandomGraph;
import lib.random.RandomGraphNodeCount;
import lib.random.RandomGraphEdgeCount;

NodeCount() = 10;
EdgeCount() = 10;

DirectedGraph := RandomGraph(RandomGraphNodeCount: NodeCount,
                             RandomGraphEdgeCount: EdgeCount);

@OrderBy(MyGraphPath, "col0", "col1");
MyGraphPath := GraphPath(G: DirectedGraph);