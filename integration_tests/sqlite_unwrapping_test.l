#
# Copyright 2023 Google LLC
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

@Engine("sqlite", type_checking: false);


Test("simple_assignment", {a:, b:}) :- {a:, b:} == {a: "va", b: "vb"};
Test("arrow_assignment", {a:, b:}) :- a -> b == "va" -> "vb";
Test("assignment_from_list", {a:, b:}) :-
  {a:, b:} in [{a: "va1", b: "vb1"}, {a: "va2", b: "vb2"}];
Test("assignment_from_list_with_arrow", {a:, b:}) :-
  a -> b in ["va1" -> "vb1", "va2" -> "vb2"];
Test("value_lookup", v) :-
  2 -> v in [0 -> "a", 1 -> "b", 2 -> "c", 3 -> "d"];
Test("assignment_to_one_of", b) :-
  {a: 1, b:} == {a: 1, b: "vb"};
Test("assignment_aggr_lookup", {a:, b:}) :-
  a in [0, 1],
  m == [1 -> "a", 2 -> "b"],
  b Max= (v :- a -> v in m);
Test("nested_assignment", a -> b -> c) :-
  {a:, x: {b:, z: {w: c}}} == {a: "va", x: {b: "vb", z: {w: "vc"}}};