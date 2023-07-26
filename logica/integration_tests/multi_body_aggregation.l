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

# Tests for multi-body-aggregation.

A() += 1;
A() += 2;

Engineer(x) :- x in ["e1", "e2", "ed1"];
Doctor(x) :- x in ["d1", "ed1"];

PeopleCount() Count= p :- Engineer(p);
PeopleCount() Count= p :- Doctor(p);

S("1", n? += x) distinct :- x in [1,2,3];
S("1", n? += x) distinct :- x in [10, 20];
S("2", n? += x) distinct :- x in [4,5];

@OrderBy(TestOutput, "col0");
TestOutput("A", A());
TestOutput("PeopleCount", PeopleCount());
TestOutput("S1", n) :- S("1", n:);
TestOutput("S2", n) :- S("2", n:);
