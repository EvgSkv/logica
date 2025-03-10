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

# Testing 'With' annotation.

@Engine("bigquery");

@With(Parent);
Parent("A", "B");
Parent("B", "C");
Parent("B", "D");
Parent("C", "E");

@With(AxiomGrandparent);
AxiomGrandparent("L", "M");

Grandparent(a, b) :- Parent(a, x), Parent(x, b);
Grandparent(a, b) :- AxiomGrandparent(a, b);

@OrderBy(Test, "col0", "col1");
Test(a, b) :- Grandparent(a, b);

