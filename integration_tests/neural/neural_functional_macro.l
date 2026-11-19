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

# Functional predicates as macros inside neural rules: Odds reads the
# learned predicates and Sigmoid wraps it; both must inline into P at
# the call site rather than compile as cone members. Logistic
# regression on a deterministic one-dimensional task: points x in
# -4..4, label = (x > 0), so the fit is sigmoid(w * x + b) with a
# large positive w and b near 0. The golden checks the exact loss and
# accuracy after a fixed optimization, and macro-of-macro nesting.

@Engine("duckdb");

Point(i) :- i in Range(9);
X(i) = ToFloat64(i) - 4.0 :- Point(i);
Label(i) = (if i > 4 then 1.0 else 0.0) :- Point(i);

W() = 0.0;
B() = 0.0;

Odds(x) = W() * x + B();
Sigmoid(z) = 1.0 / (1.0 + Exp(-z));
Probability(x) = Sigmoid(Odds(x));

@NoInject(P);
P(i) = Probability(X(i)) :- Point(i);

Loss() += -(Label(i) * Log(P(i) + 1e-9) +
            (1.0 - Label(i)) * Log(1.0 - P(i) + 1e-9)) / 9.0;

@NeuralTarget(Loss, learn: [W, B],
              optimizer: "adam", steps: 300, learning_rate: 0.1);

Accuracy() += (if (if P(i) > 0.5 then 1.0 else 0.0) == Label(i)
               then 1.0 else 0.0) / 9.0;

@OrderBy(Test, "col0");
Test("accuracy", Round(Accuracy(), 4));
Test("loss", Round(Loss(), 4));
Test("sign of w", Round(W() / Abs(W()), 1));
