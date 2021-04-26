#
# Copyright 2020 Google LLC
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

# **** This test fails due to inability to create named rows. ****

# Tests for reachability.l library.
# Mechanically only testing ZeroConnects, other predicates are for
# manual inspection.


@Engine("trino");

import lib.reachability.GraphPath;
import lib.reachability.GP3;
import lib.reachability.GraphDistance;
import lib.reachability.Edge;

D(a, a + 1) :- a in Range(100);

EncodeEdge(a, b) =
  SqlExpr("CAST(ROW({a}, {b}) AS ROW(source BIGINT, target BIGINT))");

@OrderBy(P, "col0", "col1");
P := GraphPath(G: D, Edge: EncodeEdge);

@OrderBy(PathTo99, "col0", "col1");
PathTo99(source, target) :-
  p == P(0, 99),
  e in p.path,
  source == e.source,
  target == e.target;

PartialPath := GP3(G: D);

PartialDistance := GraphDistance(G: D);

@OrderBy(ZeroConnects, "col0");
ZeroConnects(x, x, d) :-
  PartialPath(0, x),
  d == PartialDistance(0, x);

Test(x) :- ZeroConnects(x);