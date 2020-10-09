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

# Testing that annotations are preserved.
# Predicates are meaningless. Simply creating a deep call stack and calling the
# functor.

@Ground(L0);
L0() = 0;
L1() = L0() + 1;

@NoInject(L2);
@OrderBy(L2, "yodaql_value");
L2() = L1() + 2;

Three() = 3;

@Ground(L3);
L3 := L2(L0: Three);

L4() = L3() + L2();

@Limit(L5, 1);
L5() = L4() + 5;

H1() = 101;

I1 := L5(L0: H1);
