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

# Testing that Logica's _blinking_ behavior goes through the
# Clingo recursion.

@Engine("duckdb", clingo: {time_limit: ∞, models_limit: ∞});

@Recursive(Out, 5);

Seed("p");

# Feedback: what the fragment picked becomes blocked.
Blocked(x) distinct :- Out(x) | x == "dummy";

# ASP fragment: choice, blocked excluded. Union over models:
# {p} when p unblocked, {} when blocked -- a one-atom flip-flop.
Pick(x) couldbe :- Cand(x);
CantPick() cantbe :- Pick(x), Blk(x);

@Ground(Facts);
Facts() List= ClingoFact("Cand", [x]) :- Seed(x);
Facts() List= ClingoFact("Blk", [x]) :- Blocked(x);

M() = Clingo(["Pick", "Cand", "CantPick", "Blk"], Facts());

Out(x) distinct :-
  ExtractClingoCall(x, predicate: "Pick", model_id:) = M();

SortList(l) = Array{x -> x :- x in l};

Test(x, SortList(m.model)) :- Out(x), m in M();