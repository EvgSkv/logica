import timeline.TimelineUnionAgg;
import timeline.PulseAdd;

@Engine("duckdb");

# Intervals from different sources — aggregate union.
Source(interval: [{arg: 1.0, value: 5.0}], who: "alice");
Source(interval: [{arg: 3.0, value: 8.0}], who: "bob");
Source(interval: [{arg: 10.0, value: 15.0}], who: "carol");

# TimelineUnionAgg should merge [1,5) [3,8) [10,15) → [1,8) [10,15).
AggUnion(result? TimelineUnionAgg= interval) distinct :- Source(interval:);

# PulseAdd — aggregate pulses.
Pulse(p: [{arg: 1.0, value: 1.0}], who: "x");
Pulse(p: [{arg: 1.0, value: 2.0}], who: "y");
Pulse(p: [{arg: 5.0, value: -3.0}], who: "z");

# Should merge: 1→3.0, 5→-3.0
AggPulse(result? PulseAdd= p) distinct :- Pulse(p:);
