#
# Copyright 2026 Google LLC
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

# Keys of a neural predicate may come solely from constants in rule heads:
# the domain must include them even though no input relation exists.
# Also exercises reading the whole predicate (P(x)) inside its own rule.

@Engine("duckdb");

@Recursive(P, 3, mode: "neural");

P("a") Max= 1;
P("b") Max= 2;
P("c") Max= P(x);

@OrderBy(Test, "col0");
Test(x, v) :- v = P(x);
