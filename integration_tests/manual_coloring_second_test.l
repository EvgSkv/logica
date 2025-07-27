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

@Engine("duckdb", clingo: true);

E("a", "b");
E("b", "c");
E("a", "c");
E("c", "d");
E("d", "e");
E("e", "f");
E("f", "d");

Color("r");
Color("g");
Color("b");

N(x) :- E(x, y);
N(y) :- E(x, y);

C(n, c) couldbe :- N(n), Color(c);

Bad() cantbe :-
  N(x), Count{ c :- C(x, c) } != 1         |  # One color for each node.
  E(x, y), C(x, cx), C(y, cy), cx = cy;    ;  # Ends of the edge can't be the same.

ColoringPredicates() = ["E", "Color", "N", "C", "Bad"];

RenderColoring(model) = Join(Array{ n -> (n ++ "->" ++ c) :-
                                    m in model,
                                    m.predicate == "c",
                                    args = m.args,
                                    n = args[0],
                                    c = args[1] }, " ");

@With(Model);
Model(m) :- m in Clingo(ColoringPredicates(), []);

Colorings(m.model_id) = RenderColoring(m.model) :-
  Model(m);