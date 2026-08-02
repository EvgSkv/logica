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

# Basic test of neural execution: elementwise iteration over integer keys,
# no string indexing involved.
# V(x) grows by 1 per iteration until it hits the ceiling 10 * x, so the
# stable state is exactly V(x) = 10 * x. Values are integral, golden is exact.

@Engine("duckdb");

@Recursive(V, mode: "neural");

N(x) :- x in Range(5);

V(x) Max= 0 :- N(x);
V(x) Max= Least(V(x) + 1, 10 * x) :- N(x);

@OrderBy(Test, "col0");
Test(x, v) :- N(x), v = V(x);
