#
# Copyright 2023 Google LLC
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

@Engine("sqlite", type_checking: true);

T(a: 1, b: 2);
T(a: 3, b: 4);

D(..r) :- T(..r), r.a == 1;

E(two_a: 2 * a) :- T(a:);

F(a) = {a:, b: 2 * a} :- a = 5;

@OrderBy(Test, "a", "ta");
Test(a: r.a, b: r.b, r:, c:, two_a_record:, ta: two_a_record.two_a,
     f:) :-
  D(a: c), T(..r), E(..two_a_record), F(..f);