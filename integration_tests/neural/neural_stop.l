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

# A stop predicate rides the neural iteration as a satellite and breaks
# it when it derives a row: the wave walks a chain of 5000 and the
# iteration halts right after the frontier passes 1500 -- far before
# the chain ends. The golden pins the exact stopping point under the
# current STOP_CADENCE.

@Engine("duckdb");

@Recursive(D, 100000, stop: StopNow, satellites: [Frontier], mode: "neural");

Edge(x, x + 1) :- x in Range(5000);
D(0) Max= 0.0;
D(y) Max= D(x) + 1.0 :- Edge(x, y);
Frontier() Max= D(x);
StopNow() += 1.0 :- Frontier() > 1500.5;

Test(Frontier());
