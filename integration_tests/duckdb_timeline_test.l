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

# Timeline extension test.
# You need to install extension first.

@Extension("timeline");

TimelineUnion(a, b) = SqlExpr("TimelineUnion({a}, {b})", {a:, b:});
TimelineIntersect(a, b) = SqlExpr("TimelineIntersect({a}, {b})", {a:, b:});
TimelineUnionAgg(a) = SqlExpr("TimelineUnionAgg({a})", {a:});
TimelineIntersectAgg(a) = SqlExpr("TimelineIntersectAgg({a})", {a:});
TimelineRender(a) = SqlExpr("TimelineRender({a})", {a:});

A() = [1 -> 3, 7 -> 10, 13 -> 14, 17 -> 19];
B() = [2 -> 4, 15 -> 18];

T("A") = A();
T("B") = B();
T("u") = TimelineUnion(A(), B());
T("i") = TimelineIntersect(A(), B());
T("a") = TimelineUnionAgg{ x :- {x:} in [{x:[1->2]}, {x:[3->4]}, {x:[2->3]}]};
T("I") = TimelineIntersectAgg{ x :- {x:} in [ {x: [1 -> 5]}, {x: [3 -> 10]}] };

R(x) = TimelineRender(T(x));

@OrderBy(Test, "col0");
Test(x) = R(x);