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

@Engine("duckdb");

Edge(1, 2);
Edge(2, 3);
Edge(3, 4);
Edge(4, 5);
Edge(5, 6);
Edge(6, 7);
Edge(7, 8);
Edge(8, 9);
Edge(9, 10);

TC(x, y) :- Edge(x, y);
TC(x, y) :- TC(x, z), Edge(z, y);

@Recursive(TC, -1, mode: "diamond");

@OrderBy(Test, "col0", "col1");
Test(x, y) :- TC(x, y);
