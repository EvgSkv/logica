#
# Copyright 2025 Google LLC
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

# There is no direct connection of Logica context in tests for now.
# So this test is for manual execution.

@Engine("duckdb", clingo: true);

############################
# Graph coloring program.
Color("red");
Color("green");
Color("blue");
C(x, y) couldbe :- V(x), Color(y);
N() cantbe :-
  E(a, b), C(a, x), C(b, x) |  # Ends of an edge must be different.
  C(x, a), C(x, b), a != b  |  # No more than one color per node.
  V(x), ~Colored(x)         ;  # Everything must be colored.
Colored(x) :- C(x, c);
GraphColoringPredicates() = ["Color", "C", "N", "Colored"];

###############
# Some data.
V(x) :- x in ["a", "b", "c", "d"];
E(x, y) :- t = ["a", "b", "c"], x in t, y in t, x != y;
E("c", "d");

DataFacts() = List{ClingoFact("V", [x]) :- V(x)} ++
              List{ClingoFact("E", [a, b]) :- E(a, b)};

Models() = Clingo(GraphColoringPredicates(), DataFacts());

Coloring(model_id) Array= node -> color :-
  ExtractClingoCall(node, color, predicate: "C", model_id:) = Models();

@OrderBy(Test, "logica_value");
Test() = Coloring();