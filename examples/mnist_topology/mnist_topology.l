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

# Neurosymbolic MNIST: the perceptron of examples/mnist with eyes for
# topology.
#
# A digit "8" has two holes, "0", "6" and "9" have one, "1" and "7" have
# none — but a perceptron sees pixels, not holes, and happily reads a
# strangely written 8 as a 7. Holes, however, are a reachability
# question, and reachability is what Datalog recursion does. This
# program counts the holes of every digit by a recursive rule, feeds the
# counts to the network as four extra input pixels, and trains the same
# perceptron otherwise.
#
# Region labeling in one Min= recursion: the background enters from the
# border of the frame carrying label -1, every blank cell offers its own
# cell number, ink is impassable (sentinel 999999), and labels flow
# between neighbors taking the minimum. At stabilization a blank cell
# reachable from the border holds -1, and a hole holds the smallest cell
# number of its component: holes are the labels in [0, 999999).
#
# The whole pipeline — ink, holes, inputs, network — is written once,
# over the training data; test-set evaluation is a single functor call
# substituting the test data. The learned parameters do not depend on
# the substituted data, so the evaluation reads the same trained
# tables, while the hole-counting recursion is copied and recomputes
# the holes of the test images.
#
# Run with: examples/mnist_topology/run_mnist_topology.sh
# (shares the /tmp/logica_mnist dataset with examples/mnist).

@Engine("duckdb");

@AttachDatabase("mnist", "/tmp/logica_mnist/mnist.duckdb");

@Ground(TrainPixelData, "mnist.train_pixel");
@Ground(TrainLabelData, "mnist.train_label");
@Ground(TestPixelData, "mnist.test_pixel");
@Ground(TestLabelData, "mnist.test_label");

s(x) = ToString(x);
Take(x) = Coalesce(AnyValue(x), 0);

Coordinate(i) :- i in Range(28);
Edge(0);
Edge(27);
InputId(i) :- i in Range(788);  # 784 pixels and 4 topology features.
PixelId(i) :- i in Range(784);
HiddenNeuron(j) :- j in Range(100);
Digit(d) :- d in Range(10);
TrainExample(e) :- e in Range(60000);
TestExample(e) :- e in Range(10000);

Ink() = 999999.0;

# ======================= The symbolic part: holes =======================

TrainInk(e, i, j) = 1.0 :-
  v == TrainPixelData(e, p), v > 0.25, TrainExample(e),
  i == (p - p % 28) / 28, j == p % 28;

TrainBlocked(e, i, j) = Take{TrainInk(e, i, j)} > 0.5;

@Recursive(TrainRegion, mode: "neural");
TrainRegion(e, i, j) Min= (if TrainBlocked(e, i, j) then Ink() else -1.0) :-
  TrainExample(e), Coordinate(i), Coordinate(j), (Edge(i) | Edge(j));
TrainRegion(e, i, j) Min= (if TrainBlocked(e, i, j)
                           then Ink() else i * 28.0 + j) :-
  TrainExample(e), Coordinate(i), Coordinate(j);
# Labels flow between 4-neighbors: strictly 4, an 8-connected background
# would leak through diagonal gaps in the ink and dissolve holes.
TrainRegion(e, i, j) Min= (if TrainBlocked(e, i, j)
                           then Ink() else TrainRegion(e, i + di, j + dj)) :-
  TrainExample(e), Coordinate(i), Coordinate(j),
  di in [-1, 0, 1], dj in [-1, 0, 1], Abs(di) + Abs(dj) == 1;


# A hole is a region that neither reached the border nor is ink.
TrainHoleComponent(e, l) distinct :-
  l == TrainRegion(e, i, j), l >= 0.0, l < Ink();
TrainHoleCount(e) += 1 :- TrainHoleComponent(e, l);
TrainHoleArea(e) += 1 :-
  l == TrainRegion(e, i, j), l >= 0.0, l < Ink();


# ================ The neural part: the same perceptron ================

# Inputs 0..783 are the pixels; 784..786 one-hot the number of holes
# (none, one, two or more); 787 is the total hole area.
TrainInput(e, i) = 0.0 + TrainPixelData(e, i) :-
  TrainExample(e), PixelId(i);
TrainInput(e, 784) = (if Take{TrainHoleCount(e)} == 0 then 1.0 else 0.0) :-
  TrainExample(e);
TrainInput(e, 785) = (if Take{TrainHoleCount(e)} == 1 then 1.0 else 0.0) :-
  TrainExample(e);
TrainInput(e, 786) = (if Take{TrainHoleCount(e)} >= 2 then 1.0 else 0.0) :-
  TrainExample(e);
TrainInput(e, 787) = Least(1.0, Take{TrainHoleArea(e)} / 60.0) :-
  TrainExample(e);


TrainLabel(e, d) distinct :-
  TrainLabelData(e, d), TrainExample(e), Digit(d);
TestLabel(e, d) distinct :-
  TestLabelData(e, d), TestExample(e), Digit(d);

LeakyRelu(z) = Greatest(z, 0.1 * z);

W1(i, j) = 0.05 * NormalHash("w1-" ++ s(i) ++ "-" ++ s(j)) :-
  InputId(i), HiddenNeuron(j);
HiddenBias(j) = 0.0 :- HiddenNeuron(j);
W2(j, d) = 0.1 * NormalHash("w2-" ++ s(j) ++ "-" ++ s(d)) :-
  HiddenNeuron(j), Digit(d);
OutputBias(d) = 0.0 :- Digit(d);

Hidden(e, j) = LeakyRelu(HiddenBias(j) +
                         Sum{TrainInput(e, i) * W1(i, j)}) :-
  TrainExample(e), HiddenNeuron(j);

Score(e, d) = OutputBias(d) + Sum{Hidden(e, j) * W2(j, d)} :-
  TrainExample(e), Digit(d);

# Cross-entropy of an example: log-sum-exp of all scores minus the
# score of the true class.
Loss() += (Log(Sum{Exp(Score(e, d2))}) - Score(e, d)) / 60000.0 :-
  TrainLabel(e, d);

@NeuralTarget(Loss, learn: [W1, HiddenBias, W2, OutputBias],
              steps: 1200, learning_rate: 0.5, epsilon: 1e-9);

# ================= Evaluation: the network as a functor =================
# The whole test half of the program — hole counting by the recursive
# rule included — is the same network applied to the test data. The
# learned parameters do not depend on the substituted data, so the copy
# reads the same trained tables; the recursion island is copied and
# recomputes the holes of the test images.

TestScore := Score(TrainPixelData: TestPixelData, TrainExample: TestExample);

Predicted(e) ArgMax= d -> TestScore(e, d);

@Ground(SavedPrediction, "mnist.prediction_topology");
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
