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

# Computing PageRank recursively.
# https://en.wikipedia.org/wiki/PageRank

@Engine("sqlite");

# Data.
Link("a", "b");
Link("a", "c");
Link("c", "d");
Link("e", "d");
Link("h", "d");
Link("d", "i");
Link("d", "j");
Link("j", "d");
Link("i", "a");

Link("f", "g");
Link("g", "f");

# Auxiliary predicates.
Vertex(x) distinct :- Link(a, b), (x == a | x == b);
Degree(x) += 1.0 :- Link(x);
NumVertices() += 1 :- Vertex();

# Computing PageRank.
PageRank(x) += 1.0 :- Vertex(x);
PageRank(y) += 0.5 * PageRank(x) /  Degree(x) :-
  Link(x, y);

Test := PageRank();

# Predicates for debugging:
Flow(a, b) = 0.5 * PageRank(a) / Degree(a) :- Link(a, b);

TotalMass() += PageRank();

PageRankProbability(x) = PageRank(x) / TotalMass();

PageRankCheckStep(x) += 0.5 / NumVertices() :- Vertex(x);
PageRankCheckStep(y) += 0.5 * PageRankProbability(x) / Degree(x) :-
  Link(x, y);
