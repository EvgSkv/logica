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

@Engine("psql");

F(x) --> 2 * x;
G(x, y) --> List{{a: x * y, b: i} :- i in Range(y + 1)};

S(a, b) --> (if a is null then b else "(" ++ a ++ ":" ++ b ++ ")");
@BareAggregation(BareA, semigroup: S);
A(x) = a :- a = BareA(x), a ~ S();

@OrderBy(Test, "col0", "col1");
Test(i, j, F(i), G(i, j),
     A{ c :- c in [ToString(i), "a", "b", "c", ToString(j)] }) :-
  i in Range(3), j in Range(4);