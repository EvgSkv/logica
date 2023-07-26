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

# Testing PostgreSQL engine.


@Engine("psql");

Parent("A", "B");
Parent("B", "C");
Parent("C", "D");
Parent("B", "E");
Parent("A", "F");
Parent("A", "G");
Parent("G", "H");

ChildrenOf(parent) List= child :-
  Parent(parent, child);

NumChildren(parent) += 1 :-
  Parent(parent);

Grandparent(a, b) :-
  Parent(a, x), Parent(x, b);

@OrderBy(Test, "col0", "col1", "col2");
Test("Parent", parent, child) :- Parent(parent, child);
Test("Grandparent", a, b) :- Grandparent(a, b);
Test("NumChildren", parent, ToString(NumChildren(parent)));
Test("ChildrenOf", parent, ArrayToString(ChildrenOf(parent), ","));

