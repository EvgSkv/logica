#
# Copyright 2024 Google LLC
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

@Engine("duckdb");

Move("a", "b");
Move("b", "a");
Move("b", "c");
Move("c", "d");

Node(x) distinct :- Move(a, b), x in [a, b];

N() += N();
N() += 1;

@Recursive(Win, 101, satellites: [SmoothedWin, N]);
Win(x) :- Move(x, y), ~Win(y);

SmoothedWin(x) += SmoothedWin(x) * (N() - 1) / N();
SmoothedWin(x) += ToFloat64(!~ Win(x)) / N() :- Node(x);

@OrderBy(Test, "col0");
Test(x, SmoothedWin(x));
