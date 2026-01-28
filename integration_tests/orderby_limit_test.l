#
# Copyright 2025 Google LLC
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

# Tests for annotating denotations.

P1((x * 17) % 39) order_by("col0") limit(5) :- x in Range(10);
P2(37) limit(2) :- x in Range(10);
P3((x * 3) % 7) order_by("col0") :- x in Range(4);

@OrderBy(Test, "col0", "col1");
Test("P1", x) :- P1(x);
Test("P2", x) :- P2(x);
Test("P3", x) :- P3(x);
