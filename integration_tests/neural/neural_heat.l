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

# Heat diffusion on a path of nodes over time. Node identifiers and time
# steps overlap as numbers (2 is both a node and a moment), but they are
# unrelated column classes and each axis numbers its own values — the
# whole point of per-axis numbering. Boundaries lose heat: a missing
# neighbor is read as zero.

@Engine("duckdb");

Node(x) :- x in Range(5);
Moment(t) :- t in Range(4);

Neighbor(x, y) = 1.0 :- Node(x), Node(y), Abs(x - y) == 1;

@Recursive(Heat, mode: "neural");

Heat(x, 0) = (if x == 2 then 90.0 else 10.0) :- Node(x);

Heat(x, t + 1) = 0.5 * Heat(x, t) +
                 0.25 * Sum{Heat(y, t) * Neighbor(x, y)} :-
  Node(x), Moment(t);

@OrderBy(Test, "col0", "col1");
Test(t, x, h) :- t in [0, 2, 4], h = Round(Heat(x, t), 2);
