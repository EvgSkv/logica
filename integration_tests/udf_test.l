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

# Testing simple function compilation.

# Functors of argument F.
GridF(t) = F(t) :- t == s / 100.0 - 5, s in Range(1000);
FunctionMinimum() = x :-
  x ArgMin= t -> GridF(t);

F1(x) --> (x - 3) ^ 2 + 4;
F2(x) --> (x + 2) ^ 2 * 5 - 8;

Min1 := FunctionMinimum(F: F1);
Min2 := FunctionMinimum(F: F2);

Test("f1") = Min1();
Test("f2") = Min2();
