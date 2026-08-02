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

# Linear regression via @NeuralTarget: the canonical acyclic learning
# cone. The data is generated without noise from known weights, so the
# unique least-squares optimum is exactly TrueWeight: gradient descent
# must recover 2, -1, 0.5 and drive the loss to zero.
#
# The definition of Weight is its initialization (NormalHash makes it
# deterministic); after training every reader of Weight sees the learned
# values.

@Engine("duckdb");

s(x) = ToString(x);

Feature(f) :- f in Range(3);
Example(e) :- e in Range(12);

X(e, f) = NormalHash("x-" ++ s(e) ++ "-" ++ s(f)) :- Example(e), Feature(f);

TrueWeight(0) = 2.0;
TrueWeight(1) = -1.0;
TrueWeight(2) = 0.5;

Actual(e) += X(e, f) * TrueWeight(f);

Weight(f) = NormalHash("w-" ++ s(f)) :- Feature(f);

Prediction(e) += X(e, f) * Weight(f);

Loss() += (Prediction(e) - Actual(e)) ^ 2;

@NeuralTarget(Loss, learn: [Weight],
              steps: 30000, learning_rate: 0.01, epsilon: 1e-14);

@OrderBy(Test, "col0");
Test("loss", Round(Loss(), 6));
Test("w" ++ s(f), w) :- w = Round(Weight(f), 3);
