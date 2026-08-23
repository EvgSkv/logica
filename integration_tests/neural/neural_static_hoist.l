#
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# The static part of a recursive rule is hoisted out of the sweep: a
# variable that only witnesses the rule (bound by an input relation and
# compared to a key, like s in `Special(s), s != x`) is summed out once,
# before the iteration, instead of becoming a dense axis in every sweep.
# The results must agree with the SQL engine, witness multiplicities
# included.

@Engine("duckdb");

Node(1);
Node(2);
Node(3);
Node(4);
Special(2);
Special(4);

# Sum: every witness s != x is a separate derivation, so x gains the
# number of its witnesses per round.
@Recursive(Hits, 3, mode: "neural");
Hits(x) += Hits(x) :- Node(x);
Hits(x) += 1 :- Node(x), Special(s), s != x;

# Max: witnesses do not multiply.
@Recursive(Best, 3, mode: "neural");
Best(x) Max= 0 :- Node(x);
Best(x) Max= Best(x) + 1 :- Node(x), Special(s), s != x;

# Not hoistable: the witness enters the value.
@Recursive(Total, 3, mode: "neural");
Total(x) += Total(x) :- Node(x);
Total(x) += s :- Node(x), Special(s), s != x;

@OrderBy(Test, "x");
Test(x:, hits: Hits(x), best: Best(x), total: Total(x)) :- Node(x);
