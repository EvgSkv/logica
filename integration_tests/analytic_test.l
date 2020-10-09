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

# Testing analytic functions.

Ten() = x :- x in Range(10);

Data("one_five", x, y) :-
  x == Ten(),
  y == ToInt64(x == 1 || x == 5);

Data("three_four_nine", x, y) :-
  x == Ten(),
  y == ToInt64(x == 3 || x == 4 || x == 9);

@OrderBy(DataSum, "col0", "col1");
DataSum(n, x, y) Aggregate= CumulativeSum(y, [n], [n, x]) :-
  Data(n, x, y);

@OrderBy(DataWindowedSum, "col0", "col1");
DataWindowedSum(n, x, y) Aggregate= WindowSum(y, [n], [n, x], 3) :-
  Data(n, x, y);

@OrderBy(NonzeroMax, "col0", "col1");
NonzeroMax(n, x, y) Aggregate= WindowMax(x * y, [n], [x], 3) :- Data(n, x, y);

Test(DataSum, n, x, y) = DataSum(n, x, y);
Test(DataWindowedSum, n, x, y) = DataWindowedSum(n, x, y);
Test(NonzeroMax, n, x, y) = NonzeroMax(n, x, y);

@OrderBy(ReadableTest, "test_name", "customer", "x");
ReadableTest(test_name: p.predicate_name,
             customer:,
             x:,
             y:,
             aggregate:) :- Test(p, customer, x, y) == aggregate;

