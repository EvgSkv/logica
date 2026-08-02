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

# Conway's Game of Life as a neural iteration, with time as a key:
# Life(x, y, n + 1) is defined via Life(x, y, n). Every sweep of the
# rewrite recomputes the whole history and extends it by one generation,
# so the program is a genuine fixpoint: once all layers up to the Steps
# horizon are built, the iteration stabilizes on its own.
#
# Life exercises four corners of the neural fragment:
#   * computed head keys (n + 1) become synthetic constrained axes;
#   * unnesting a literal list (dx in [-1, 0, 1]) is a bounded domain:
#     an axis with a membership mask;
#   * birth/survival logic is integer arithmetic: for an integer count c
#     the indicator of c == k is Greatest(0, 1 - Abs(c - k));
#   * neighbor reads Life(x + dx, y + dy, n) are key shifts compiling
#     into constraint joins; outside the grid they do not join (no torus).
#
# The initial blinker is horizontal; generations oscillate
# horizontal / vertical / horizontal / ...

@Engine("duckdb");

Cell(x, y) :- x in Range(5), y in Range(5);
Steps(n) :- n in Range(7);

Init(2, 1);
Init(2, 2);
Init(2, 3);

@Recursive(Life, mode: "neural");

Life(x, y, 0) Max= 1 :- Init(x, y);
Life(x, y, 0) Max= 0 :- Cell(x, y);

Life(x, y, n + 1) Max= alive :-
  Cell(x, y), Steps(n),
  c = Neighbors(x, y, n),
  a = Life(x, y, n),
  alive = (if c == 3 then 1 else if a == 1 && c == 2 then 1 else 0);

Neighbors(x, y, n) += Life(x + dx, y + dy, n) :-
  Cell(x, y),
  dx in [-1, 0, 1], dy in [-1, 0, 1],
  Abs(dx) + Abs(dy) != 0;

@OrderBy(Test, "col0", "col1", "col2");
Test(n, x, y) :- n in [0, 1, 2], Life(x, y, n) == 1;
