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

Person("John");
Person("Mary");
Person("Jessica");
Person("James");

Loves("Mary", "John");
Loves("John", "Mary");
Loves("Jessica", "James");

Proposes(a, b) couldbe :- Person(a), Person(b), a != b;

Impossible() cantbe :-
  Person(a), Count{ b :- Proposes(a, b) } != 1;

Happy(a) :- Loves(a, b), Proposes(b, a);

Village() = ["Person", "Loves", "Proposes", "Happy",
             "Impossible"];

Worlds() = Clingo(Village(), []);

ProposesInWorld(a, b, world_id:) :-
  ExtractClingoCall(a, b, predicate: "Proposes", world_id:) = Worlds();

HappyInWorld(person:, world_id:) :-
  ExtractClingoCall(person, predicate: "Happy", world_id:) = Worlds();

Test(person:, world_id:) :- HappyInWorld(person:, world_id:);