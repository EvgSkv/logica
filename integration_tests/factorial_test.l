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


Prod(x) = Exp(Sum(Log(x)));

Factorial(x) = Round(f) :-
  f Prod= (n + 1 :- n in GenerateArray(0, x - 1));

@OrderBy(Test, "col0");
Test(Factorial(2));
Test(Factorial(3));
Test(Factorial(4));
Test(Factorial(5));
