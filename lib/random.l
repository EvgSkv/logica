# Generating random things.
# For now we only generate random graph.

# For example of usage see examples/scripts/closure_use.l.

RandomGraphSeed() = "";
RandomGraphNodeCount() = 10;
RandomGraphEdgeCount() = 20;

PositiveFingerprint(salt, item) -->
  Abs(FarmFingerprint(salt ++ ToString(item)));

RandomEdge(seed:) --> {
    source: PositiveFingerprint(RandomGraphSeed() ++ "-edge-start-", seed) %
      RandomGraphNodeCount(),
    target: PositiveFingerprint(RandomGraphSeed() ++ "-edge-end-", seed) %
      RandomGraphNodeCount()
  };

RandomGraph(edge.source, edge.target) :-
  edge == RandomEdge(seed:),
  seed in Range(RandomGraphEdgeCount());
 

