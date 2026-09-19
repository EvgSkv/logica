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


# Learning edge lengths from observed shortest distances: the gradient
# flows through the Min= recursion, i.e. along the shortest paths
# themselves. Edges on no shortest path receive no gradient — their
# lengths are not identifiable and only the distances are checked.

@Engine("duckdb");

Edge(0, 1);
Edge(0, 2);
Edge(1, 2);
Edge(2, 3);
Edge(1, 3);
Edge(3, 4);
Edge(0, 4);

ObservedDistance(0) = 0.0;
ObservedDistance(1) = 1.0;
ObservedDistance(2) = 3.0;
ObservedDistance(3) = 4.0;
ObservedDistance(4) = 5.0;

Node(x) distinct :- Edge(x, y);
Node(y) distinct :- Edge(x, y);

W(x, y) = 3.0 :- Edge(x, y);

@Recursive(Dist, 30, mode: "neural");
Dist(0) Min= 0.0;
Dist(y) Min= Dist(x) + W(x, y) :- Edge(x, y);

Loss() += (Dist(x) - ObservedDistance(x)) ^ 2 :- Node(x);

@NeuralTarget(Loss, learn: [W],
              steps: 3000, learning_rate: 0.05, epsilon: 1e-14);

@OrderBy(Test, "col0");
Test("d" ++ ToString(x), d) :- d = Round(Dist(x), 3);
Test("loss", Round(Loss(), 6));
