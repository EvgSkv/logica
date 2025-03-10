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

# Testing non-trivial rest-of field.

@Engine("bigquery");

T(a: 1, b: 2, c: 3, d: "a");
T(a: 4, b: 5, c: 6, d: "b");
T(a: 7, b: 8, c: 9, d: "c");

# Take T, recalculate column a and remove column b.
@OrderBy(Test, "d");
Test(a: 2 * a, ..r) :- T(a:, b:, ..r);
