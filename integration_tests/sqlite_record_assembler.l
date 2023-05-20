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

# Testing SQLite record introspection.

@Engine("sqlite");

Test(1, AssembleRecord(["planet" -> "Earth", "species" -> "Humans"]));
Test(2, DisassembleRecord({planet: "Mars", species: "Apes"}));
Test(3, result) :-
  r = {fire: 1, water: 2, air: 3},
  dr = DisassembleRecord(r),
  a List= (f :- f -> v in dr),
  b += (v :- f -> v in dr),
  k = Join(a, "_"),
  result = AssembleRecord([k -> b]);