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

# A ten-layer perceptron with no hand-unrolled layers: the layer is a key
# and the network is a recursive predicate. The learning cone contains a
# recursion loop; the forward probe finds its stabilization depth and the
# gradient flows through a scan of that length — recursion that is simply
# a loop compiles into simply a loop.

@Engine("duckdb");

s(x) = ToString(x);

Neuron(j) :- j in Range(3);
Layer(n) :- n in Range(10);
Example(e) :- e in Range(2);

InputValue(0, 0) = 1.0;
InputValue(0, 1) = 0.0;
InputValue(0, 2) = -1.0;
InputValue(1, 0) = -0.5;
InputValue(1, 1) = 1.0;
InputValue(1, 2) = 0.5;

Actual(0) = 1.0;
Actual(1) = -1.0;

LeakyRelu(z) = Greatest(z, 0.1 * z);

Weight(i, j, n) = 0.8 * NormalHash("w" ++ s(i) ++ "-" ++ s(j) ++ "-" ++ s(n)) :-
  Neuron(i), Neuron(j), Layer(n);
Bias(j, n) = 0.0 :- Neuron(j), Layer(n);

Activation(e, j, 0) = InputValue(e, j);
Activation(e, j, n + 1) = LeakyRelu(Bias(j, n) +
                                    Sum{Activation(e, i, n) *
                                        Weight(i, j, n)}) :-
  Example(e), Neuron(j), Layer(n);

Output(e) = Activation(e, 0, 10);

Loss() += (Output(e) - Actual(e)) ^ 2;

@NeuralTarget(Loss, learn: [Weight, Bias],
              steps: 2000, learning_rate: 0.1);

@OrderBy(Test, "col0");
Test("loss", Round(Loss(), 4));
Test("output" ++ s(e), Round(Output(e), 2)) :- Example(e);
