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

# A staircase light with two switches: the light is on iff exactly one
# switch is up — XOR, the canonical function a linear model cannot
# represent while a perceptron with one hidden layer can (Minsky &
# Papert). Two contenders train on the same four examples: the linear
# model provably bottoms out at loss 1.0, the MLP reaches 0.0. The
# golden thus pins both the theorem and the network. Also the first test
# with two @NeuralTarget's in one program.

@Engine("duckdb");

s(x) = ToString(x);

Example(e) :- e in Range(4);

SwitchOne(e) = e % 2 :- Example(e);
SwitchTwo(e) = (e - e % 2) / 2 :- Example(e);
LightOn(e) = (if SwitchOne(e) == SwitchTwo(e) then 0 else 1);

InputValue(e, 0) = SwitchOne(e);
InputValue(e, 1) = SwitchTwo(e);
InputValue(e, 2) = 1.0 :- Example(e);

# The linear contender.
LinearWeight(i) = NormalHash("lw" ++ s(i)) :- i in Range(3);
LinearOutput(e) += InputValue(e, i) * LinearWeight(i);
LinearLoss() += (LinearOutput(e) - LightOn(e)) ^ 2;

@NeuralTarget(LinearLoss, learn: [LinearWeight],
              steps: 4000, learning_rate: 0.05);

# The perceptron: one hidden layer, leaky relu.
Neuron(j) :- j in Range(4);
Layer(n) :- n in Range(2);

LeakyRelu(z) = Greatest(z, 0.1 * z);

Weight(i, j, n) = 0.8 * NormalHash("w" ++ s(i) ++ "-" ++ s(j) ++ "-" ++ s(n)) :-
  Neuron(i), Neuron(j), Layer(n);
Bias(j, n) = 0.0 :- Neuron(j), Layer(n);

Activation(e, j, 0) = InputValue(e, j);
Activation(e, j, n + 1) = LeakyRelu(Bias(j, n) +
                                    Sum{Activation(e, i, n) *
                                        Weight(i, j, n)}) :-
  Example(e), Neuron(j), Layer(n);

MlpOutput(e) = Activation(e, 0, 2);
MlpLoss() += (MlpOutput(e) - LightOn(e)) ^ 2;

@NeuralTarget(MlpLoss, learn: [Weight, Bias],
              steps: 8000, learning_rate: 0.1);

@OrderBy(Test, "col0");
Test("linear_loss", Round(LinearLoss(), 2));
Test("mlp_loss", Round(MlpLoss(), 2));
Test("light" ++ s(e), Round(MlpOutput(e), 1) + 0.0) :- Example(e);
