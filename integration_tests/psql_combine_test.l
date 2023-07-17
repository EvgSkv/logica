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

# Testing combine expressions that could be ambigous in SQLite.
@Engine("psql");

T(1);
T(2);
T(3);
T(4);

@With(R);
R(x, l) :- T(x), l == (if x == 2 || x == 3 then [x] else []);

P1(x, y) :- T(x), y += x;
P2(x, col1? List= y) distinct :- T(x), y in [1,2,3,4], R(x, l), ~(y in l);

# Test("1", x, y) :- P1(x, y);
# Test("2", x, y) :- P2(x, y);

Test() = (if true then [1] else []);