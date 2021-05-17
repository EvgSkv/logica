#
# Copyright 2020 Google LLC
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

# Testing recursion with SQLite engine.

@Engine("sqlite");

Edge(1, 2);
Edge(2, 3);
Edge(3, 4);
Edge(4, 5);

Edge(6, 7);
Edge(7, 8);

Edge(9, 10);
Edge(10, 11);
Edge(9, 11);

@OrderBy(Distance, "col0", "col1");
@RecursiveDepth(Distance, 5);
Distance(a, b) Min= 1 :- Edge(a, b);

Distance(a, a) Min= 0 :- Distance(a);
Distance(a, b) Min= Distance(b, a);
Distance(a, b) Min= Distance(a, c) + Distance(c, b);

@OrderBy(ComponentOf, "col0");
ComponentOf(x) Min= y :- Distance(x, y);

@OrderBy(Analyzed, "vertex");
Analyzed(vertex: x, component: ComponentOf(x), diameter? Max= Distance(a, b)) distinct :-
  ComponentOf(a) == ComponentOf(x), ComponentOf(b) == ComponentOf(x);

Test := Analyzed();

