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

# Shortest distances via neural recursion: the rule is a (min, +) semiring
# contraction, i.e. tropical matrix squaring in JAX.
# Vertices are strings, so this test exercises indexing of string keys into
# dense tensor indices and de-indexing on write-back.
# Pairs with no path must be absent from D (support masks, not zeros).

@Engine("duckdb");

E("a", "b") = 1;
E("b", "c") = 2;
E("a", "c") = 10;
E("c", "d") = 1;
E("b", "d") = 5;

@Recursive(D, mode: "neural");

D(a, b) Min= E(a, b);
D(a, c) Min= D(a, b) + D(b, c);

@OrderBy(Test, "col0", "col1");
Test(a, b, d) :- d = D(a, b);
