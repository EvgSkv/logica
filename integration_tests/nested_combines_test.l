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

# Tests that unified combines don't confuse variables.

@Engine("bigquery");

A(x, y) :- x == (combine List= t * 2 :- t in y), B(y);
B(z) :- z == (combine List= t + 1 :- t in [1,2,3]);


C(x, y) :-
  x == (combine List= z * 3 :- z in [1,2,3]),
  y == (combine List= z * 2 :- z in x);

D(x, y) :-
  x == (
    combine List= z + r :-
      z in w,
      w == (combine List= 1000 + t :- t in y),
      r in [1, 2, 3]
  ),
  y == (combine List= t :- t in [10, 20, 30]);

# An inner combine using top-level variable.
T(1);
T(2);
E(x, y) :-
  T(a), a == 1,
  x == [a],
  y == (combine List= z :- z == (combine += a :- T(a)));

@OrderBy(Test, "col0");
Test("A", Sort(x), Sort(y)) :- A(x, y);
Test("C", Sort(x), Sort(y)) :- C(x, y);
Test("D", Sort(x), Sort(y)) :- D(x, y);
Test("E", Sort(x), Sort(y)) :- E(x, y);
