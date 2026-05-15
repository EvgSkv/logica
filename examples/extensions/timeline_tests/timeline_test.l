import timeline.TimelineUnion;
import timeline.TimelineIntersect;
import timeline.PulseSum;

@Engine("duckdb");

# Test 1: TimelineUnion of two non-overlapping intervals.
# [1,5) and [10,15) should stay as two intervals.
UnionNonOverlap() = TimelineUnion(
  [{arg: 1, value: 5}],
  [{arg: 10, value: 15}]
);

# Test 2: TimelineUnion of overlapping intervals.
# [1,10) and [5,15) should merge to [1,15).
UnionOverlap() = TimelineUnion(
  [{arg: 1, value: 10}],
  [{arg: 5, value: 15}]
);

# Test 3: TimelineIntersect of overlapping intervals.
# [1,10) and [5,15) should give [5,10).
Intersect() = TimelineIntersect(
  [{arg: 1, value: 10}],
  [{arg: 5, value: 15}]
);

# Test 4: TimelineIntersect of non-overlapping intervals.
# [1,5) and [10,15) should give empty.
IntersectEmpty() = TimelineIntersect(
  [{arg: 1, value: 5}],
  [{arg: 10, value: 15}]
);

# Test 5: PulseSum — cumulative sum of deltas.
# +1 at 0, -1 at 5, +2 at 10 → cumsum: 1, 0, 2
CumSum() = PulseSum(
  [{arg: 0, value: 1}, {arg: 5, value: -1}, {arg: 10, value: 2}]
);
