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

# Testing tensor's dimensions used as values.

s(x) = ToString(x);

M(i, j, k) :-
  i = NaturalHash("i" ++ s(n)) % 1000,
  j = NaturalHash("j" ++ s(n)) % 1000,
  k = NaturalHash("k" ++ s(n)) % 1000,
  n in Range(1000);

Alpha() = 1.0;

T(i) += Alpha() * (j + k) :- M(i, j, k);

@NeuralTarget(Loss, learn: [Alpha], learning_rate: 0.00001, epsilon: 0, steps: 1000);
Loss() += (T(i) - 1000) ^ 2 / 1000000;

X() = Alpha();

Test() = X();