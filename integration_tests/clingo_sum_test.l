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

T(i, j, v) :- i in Range(10), j in Range(10), v = 10;

S(x) :- x = ISum{ i -> j -> v :- T(i, j, v)};

Models() = Clingo(["T", "S"], []);

SM(x, model_id:) :-
  ExtractClingoCall(x, predicate: "S", model_id:) = Models();

Test(x) :- SM(x);