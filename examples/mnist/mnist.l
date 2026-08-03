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

# MNIST digit recognition in Logica.
#
# A perceptron with one hidden layer trains by gradient descent of the
# cross-entropy loss on the full training set (60000 images, 28x28
# pixels) and is then evaluated by ordinary SQL on the 10000 test
# images. Expect around 97% accuracy in a couple of minutes.
#
# Run with: examples/mnist/run_mnist.sh
# (downloads the dataset into /tmp/logica_mnist if it is not there).

@Engine("duckdb");

@AttachDatabase("mnist", "/tmp/logica_mnist/mnist.duckdb");

@Ground(TrainPixelData, "mnist.train_pixel");
@Ground(TrainLabelData, "mnist.train_label");
@Ground(TestPixelData, "mnist.test_pixel");
@Ground(TestLabelData, "mnist.test_label");

s(x) = ToString(x);

PixelId(i) :- i in Range(784);
HiddenNeuron(j) :- j in Range(100);
Digit(d) :- d in Range(10);
TrainExample(e) :- e in Range(60000);
TestExample(e) :- e in Range(10000);

# Typed wrappers of the attached tables: an external table carries no
# type signature of its own, so the wrapper rules provide one.
TrainPixel(e, i) = 0.0 + TrainPixelData(e, i) :-
  TrainExample(e), PixelId(i);
TestPixel(e, i) = 0.0 + TestPixelData(e, i) :-
  TestExample(e), PixelId(i);
TrainLabel(e, d) distinct :-
  TrainLabelData(e, d), TrainExample(e), Digit(d);
TestLabel(e, d) distinct :-
  TestLabelData(e, d), TestExample(e), Digit(d);

LeakyRelu(z) = Greatest(z, 0.1 * z);

# Learned parameters; the definitions are their initialization.
W1(i, j) = 0.05 * NormalHash("w1-" ++ s(i) ++ "-" ++ s(j)) :-
  PixelId(i), HiddenNeuron(j);
HiddenBias(j) = 0.0 :- HiddenNeuron(j);
W2(j, d) = 0.1 * NormalHash("w2-" ++ s(j) ++ "-" ++ s(d)) :-
  HiddenNeuron(j), Digit(d);
OutputBias(d) = 0.0 :- Digit(d);

# The network.
Hidden(e, j) = LeakyRelu(HiddenBias(j) +
                         Sum{TrainPixel(e, i) * W1(i, j)}) :-
  TrainExample(e), HiddenNeuron(j);

Score(e, d) = OutputBias(d) + Sum{Hidden(e, j) * W2(j, d)} :-
  TrainExample(e), Digit(d);

# Cross-entropy of an example: log-sum-exp of all scores minus the
# score of the true class.
Loss() += (Log(Sum{Exp(Score(e, d2))}) - Score(e, d)) / 60000.0 :-
  TrainLabel(e, d);

@NeuralTarget(Loss, learn: [W1, HiddenBias, W2, OutputBias],
              steps: 1200, learning_rate: 0.5, epsilon: 1e-9);

# Test-set evaluation runs as ordinary SQL over the learned tables.
TestHidden(e, j) = LeakyRelu(HiddenBias(j) +
                             Sum{TestPixel(e, i) * W1(i, j)}) :-
  TestExample(e), HiddenNeuron(j);

TestScore(e, d) = OutputBias(d) + Sum{TestHidden(e, j) * W2(j, d)} :-
  TestExample(e), Digit(d);

Predicted(e) ArgMax= d -> TestScore(e, d);

# Predictions are stored back into the dataset database: the heavy
# scoring chain runs once, the statistics below read the stored table,
# and render_report.py draws the recognized digits from it.
@Ground(SavedPrediction, "mnist.prediction");
SavedPrediction(e, p) distinct :- TestExample(e), p == Predicted(e);

Correct() += 1 :- TestLabel(e, d), SavedPrediction(e, d);
Total() += 1 :- TestLabel(e, d);

ConfusionCount(a, p) += 1 :- TestLabel(e, a), SavedPrediction(e, p);
MostConfused() ArgMax= (s(a) ++ " read as " ++ s(p)) -> n :-
  Digit(a), Digit(p), a != p, n == ConfusionCount(a, p);

Summary(correct: Correct(), total: Total(),
        accuracy: Round(100.0 * Correct() / Total(), 2),
        most_confused: MostConfused());

DigitTotal(d) += 1 :- TestLabel(e, d);
DigitCorrect(d) += 1 :- TestLabel(e, d), SavedPrediction(e, d);

@OrderBy(PerDigit, "digit");
PerDigit(digit: d, total: DigitTotal(d), correct: DigitCorrect(d),
         accuracy: Round(100.0 * DigitCorrect(d) / DigitTotal(d), 1)) :-
  Digit(d);
