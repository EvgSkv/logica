#
# Copyright 2026 Google LLC
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

# Diamond recursion stop-signal test.
#
# Stop should observe stabilization only after the intended action order
# inside a diamond iteration. This program builds a triangular table of
# values; if Stop runs too early, the recursion terminates prematurely.

@Engine("duckdb");

@OrderBy(N, "logica_value", "col0");
N(0) = 0;
N(i + 1) = 0 :- N(i) = 0;
N(i + 1) = n + 1 :- n = N(i), n < 7;

PN() = N();

@Recursive(N, mode: "diamond", stop: Stop);
Stop() :- Max{N()} == Max{PN()};

Test := N();