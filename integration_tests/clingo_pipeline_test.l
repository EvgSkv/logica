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

Square() = [ClingoFact("E", ["a", "b"]),
            ClingoFact("E", ["b", "c"]),
            ClingoFact("E", ["c", "d"]),
            ClingoFact("E", ["d", "a"])];

@Ground(Graph);
Graph("square") = Square();
Graph("square_with_diagonal") = Square() ++ [ClingoFact("E", ["b", "d"])];

######################
# Clingo!

Color("red");
Color("green");
Color("blue");

V(x) :- E(x, y);
V(y) :- E(x, y);

C(a, c) couldbe :- V(a), Color(c);

Colored(a) :- C(a, c);

Bad() cantbe :-
  V(a), Count{ c :- C(a, c) } != 1          |
  E(a, b), C(a, c), C(b, c)                 ;

ColoringPredicates() = ["Color", "V", "C", "Colored", "Bad"];

#
#######################

@Ground(Model);
Model(m.model_id, graph_id, graph) = m.model :-
  m in Clingo(ColoringPredicates(), graph),
  graph = Graph(graph_id);

Coloring(graph_id, model_id) = Array{
      a -> c :-
        call in model,
        call.predicate = "C",
        args = call.args,
        a = args[0],
        c = args[1]
    } :-
  model = Model(model_id, graph_id, graph);

@OrderBy(NumColorings, "col0");
NumColorings(graph) += 1 :- Model(model_id, graph);

Test(graph) = NumColorings(graph);