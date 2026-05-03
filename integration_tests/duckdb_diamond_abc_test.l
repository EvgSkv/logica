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

# Diamond recursion test on a 3-cycle A -> C -> B -> A.
#
# A's body reads C, B's body reads A, C's body reads B. Diamond order
# starting from main=A is [A, B, C] — each subsequent member reads the
# fresh value just written by the earlier one. After 10 iteration rounds
# A's value is 27 (3*9). The post-iteration Gauss-Seidel pass adds one
# more step, lifting A to 30.

@Engine("duckdb");

@Recursive(A, 10, mode: "diamond");
A() Max= 0;
B() Max= A() + 1;
C() Max= B() + 1;
A() Max= C() + 1;

Test() Max= A();
