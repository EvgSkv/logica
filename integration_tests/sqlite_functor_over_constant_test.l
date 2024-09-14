#
# Copyright 2024 Google LLC
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

# Testing literals as functor arguments.

@Engine("sqlite");

A() = "a";
B() = "b";

T(a: A(), b: B());

T2 := T(A: "A", B: "B");
T3 := T(A: 10, B: 20);

Test("T", a, b) :- T(a:, b:);
Test("T2", a, b) :- T2(a:, b:);
Test("T3", a, b) :- T3(a:, b:);
