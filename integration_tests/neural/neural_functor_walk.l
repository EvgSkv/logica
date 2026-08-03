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

# A functor over a neural recursion: BigWalk gets its own copy of the
# whole island — the one-sweep rules, the portal, the @Iteration and so
# its own plan — because the @Iteration's protocol (diamonds, portals,
# finals) makes the island visible to functors. Walk stops at 5,
# BigWalk walks to 12; both live in one program.

@Engine("duckdb");

Cap() = 5;

Domain(x) :- x in Range(30);

@Recursive(Walk, mode: "neural");
Walk(0) Min= 0.0;
Walk(x + 1) Min= Walk(x) + 1.0 :- Walk(x) < Cap(), Domain(x);

BigCap() = 12;
BigWalk := Walk(Cap: BigCap);

@OrderBy(Test, "walker", "x");
Test(walker: "small", x: x, value: v) :- v == Walk(x);
Test(walker: "big", x: x, value: v) :- v == BigWalk(x);
