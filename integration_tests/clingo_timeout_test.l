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

@Engine("duckdb", clingo: {time_limit: 1});

Settings(num_edges: 1500,
         num_vertices: 600);

S(x) = ToString(x);

GD(a, b) :-
  Settings(num_edges:, num_vertices:),
  i in Range(num_edges),
  a = "n" ++ S(NaturalHash("a-" ++ ToString(i)) % num_vertices),
  b = "n" ++ S(NaturalHash("b-" ++ ToString(i)) % num_vertices),
  a != b;

G(a, b) distinct :- GD(a, b);
G(b, a) distinct :- GD(a, b);

Color("red");
Color("green");
Color("blue");

Node(n) :- G(x, y), n in [x, y];

C(n, c) couldbe :- Node(n), Color(c);

Bad() cantbe :-
  Node(n), Count{ c :- C(n, c) } != 1     |
  G(a, b), C(a, x), C(b, x)               ;

Models() = Clingo(["Color", "Node", "C", "Bad"], edges) :-
  edges = List{ ClingoFact("G", [x, y]) :- G(x, y) };

NumModels() = Size(Models());

@OrderBy(CM, "model_id", "col0", "col1");
CM(n, c, model_id:) :-
  ExtractClingoCall(n, c, predicate: "C", model_id:) = Models();

Test(..r) :- CM(..r);