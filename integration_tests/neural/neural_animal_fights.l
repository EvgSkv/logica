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

# Thirty animals, sixty hand-written training fights and sixty test
# fights. Strength is a learned predicate: the Bradley-Terry logistic
# loss asks winners to be stronger than losers. The test counts how many
# held-out fights the learned strengths predict correctly.
#
# The training data contains a few honest upsets (the goose routs the
# fox, the badger takes the dog, the buffalo gores the lion), so perfect
# accuracy is not expected — transitivity must argue with them.

@Engine("duckdb");

Animal("hamster"); Animal("mouse"); Animal("sparrow"); Animal("frog");
Animal("squirrel"); Animal("rabbit"); Animal("crow"); Animal("cat");
Animal("goose"); Animal("raccoon"); Animal("fox"); Animal("badger");
Animal("eagle"); Animal("dog"); Animal("goat"); Animal("deer");
Animal("kangaroo"); Animal("wolf"); Animal("boar"); Animal("zebra");
Animal("leopard"); Animal("gorilla"); Animal("crocodile");
Animal("buffalo"); Animal("lion"); Animal("tiger"); Animal("bear");
Animal("hippo"); Animal("elephant"); Animal("whale");

# TrainingFight(a, b, winner).
TrainingFight("wolf", "rabbit", "wolf");
TrainingFight("cat", "mouse", "cat");
TrainingFight("lion", "zebra", "lion");
TrainingFight("tiger", "boar", "tiger");
TrainingFight("bear", "wolf", "bear");
TrainingFight("elephant", "lion", "elephant");
TrainingFight("whale", "elephant", "whale");
TrainingFight("hippo", "leopard", "hippo");
TrainingFight("crocodile", "goat", "crocodile");
TrainingFight("gorilla", "dog", "gorilla");
TrainingFight("fox", "goose", "goose");
TrainingFight("badger", "dog", "badger");
TrainingFight("eagle", "crow", "eagle");
TrainingFight("raccoon", "cat", "raccoon");
TrainingFight("squirrel", "hamster", "squirrel");
TrainingFight("frog", "sparrow", "frog");
TrainingFight("mouse", "hamster", "mouse");
TrainingFight("rabbit", "squirrel", "rabbit");
TrainingFight("deer", "goat", "deer");
TrainingFight("boar", "wolf", "boar");
TrainingFight("leopard", "gorilla", "gorilla");
TrainingFight("buffalo", "lion", "buffalo");
TrainingFight("tiger", "lion", "tiger");
TrainingFight("bear", "leopard", "bear");
TrainingFight("hippo", "crocodile", "hippo");
TrainingFight("elephant", "hippo", "elephant");
TrainingFight("whale", "tiger", "whale");
TrainingFight("kangaroo", "dog", "kangaroo");
TrainingFight("wolf", "kangaroo", "wolf");
TrainingFight("zebra", "deer", "zebra");
TrainingFight("gorilla", "zebra", "gorilla");
TrainingFight("crocodile", "leopard", "crocodile");
TrainingFight("lion", "gorilla", "lion");
TrainingFight("dog", "cat", "dog");
TrainingFight("fox", "rabbit", "fox");
TrainingFight("badger", "raccoon", "badger");
TrainingFight("eagle", "rabbit", "eagle");
TrainingFight("crow", "sparrow", "crow");
TrainingFight("goose", "crow", "goose");
TrainingFight("cat", "frog", "cat");
TrainingFight("raccoon", "goose", "raccoon");
TrainingFight("goat", "badger", "goat");
TrainingFight("deer", "eagle", "deer");
TrainingFight("boar", "goat", "boar");
TrainingFight("zebra", "kangaroo", "zebra");
TrainingFight("buffalo", "boar", "buffalo");
TrainingFight("bear", "buffalo", "bear");
TrainingFight("tiger", "crocodile", "tiger");
TrainingFight("whale", "hippo", "whale");
TrainingFight("elephant", "buffalo", "elephant");
TrainingFight("mouse", "sparrow", "sparrow");
TrainingFight("squirrel", "frog", "squirrel");
TrainingFight("rabbit", "crow", "rabbit");
TrainingFight("cat", "goose", "cat");
TrainingFight("fox", "badger", "badger");
TrainingFight("dog", "wolf", "wolf");
TrainingFight("kangaroo", "deer", "kangaroo");
TrainingFight("leopard", "boar", "leopard");
TrainingFight("gorilla", "crocodile", "crocodile");
TrainingFight("hamster", "frog", "frog");

# TestFight(a, b, winner).
TestFight("whale", "lion", "whale");
TestFight("elephant", "tiger", "elephant");
TestFight("hippo", "gorilla", "hippo");
TestFight("bear", "crocodile", "bear");
TestFight("buffalo", "leopard", "buffalo");
TestFight("lion", "leopard", "lion");
TestFight("tiger", "gorilla", "tiger");
TestFight("crocodile", "zebra", "crocodile");
TestFight("gorilla", "boar", "gorilla");
TestFight("leopard", "wolf", "leopard");
TestFight("buffalo", "zebra", "buffalo");
TestFight("zebra", "wolf", "zebra");
TestFight("boar", "deer", "boar");
TestFight("wolf", "fox", "wolf");
TestFight("kangaroo", "goat", "kangaroo");
TestFight("deer", "dog", "deer");
TestFight("goat", "dog", "goat");
TestFight("dog", "fox", "dog");
TestFight("eagle", "cat", "eagle");
TestFight("badger", "cat", "badger");
TestFight("fox", "cat", "fox");
TestFight("raccoon", "rabbit", "raccoon");
TestFight("goose", "rabbit", "goose");
TestFight("crow", "mouse", "crow");
TestFight("cat", "sparrow", "cat");
TestFight("rabbit", "frog", "rabbit");
TestFight("squirrel", "mouse", "squirrel");
TestFight("frog", "mouse", "frog");
TestFight("sparrow", "hamster", "sparrow");
TestFight("squirrel", "sparrow", "squirrel");
TestFight("fox", "raccoon", "fox");
TestFight("badger", "eagle", "eagle");
TestFight("eagle", "goose", "eagle");
TestFight("dog", "raccoon", "dog");
TestFight("goat", "fox", "goat");
TestFight("deer", "badger", "deer");
TestFight("kangaroo", "eagle", "kangaroo");
TestFight("wolf", "goat", "wolf");
TestFight("boar", "kangaroo", "boar");
TestFight("zebra", "boar", "zebra");
TestFight("leopard", "deer", "leopard");
TestFight("gorilla", "kangaroo", "gorilla");
TestFight("crocodile", "buffalo", "buffalo");
TestFight("lion", "crocodile", "lion");
TestFight("tiger", "buffalo", "tiger");
TestFight("bear", "lion", "bear");
TestFight("hippo", "tiger", "hippo");
TestFight("elephant", "bear", "elephant");
TestFight("whale", "bear", "whale");
TestFight("hippo", "bear", "hippo");
TestFight("elephant", "crocodile", "elephant");
TestFight("whale", "buffalo", "whale");
TestFight("lion", "boar", "lion");
TestFight("tiger", "leopard", "tiger");
TestFight("wolf", "badger", "wolf");
TestFight("fox", "squirrel", "fox");
TestFight("cat", "rabbit", "cat");
TestFight("raccoon", "crow", "raccoon");
TestFight("goose", "squirrel", "goose");
TestFight("crow", "frog", "crow");

TrainingResult(winner, loser) distinct :-
  TrainingFight(a, b, winner),
  loser == (if winner == a then b else a);

TestResult(winner, loser) distinct :-
  TestFight(a, b, winner),
  loser == (if winner == a then b else a);

# Strength is learned; NormalHash is the deterministic initialization.
Strength(a) = NormalHash(a) :- Animal(a);

# Bradley-Terry: the log-likelihood of the winner being stronger.
Loss() += Log(1.0 + Exp(Strength(loser) - Strength(winner))) :-
  TrainingResult(winner, loser);

@NeuralTarget(Loss, learn: [Strength], steps: 3000, learning_rate: 0.1);

CorrectlyPredicted() += 1 :-
  TestResult(winner, loser), Strength(winner) > Strength(loser);
TotalTest() += 1 :- TestResult(winner, loser);

Champion() ArgMax= a -> Strength(a);
Underdog() ArgMin= a -> Strength(a);

AnyResult(winner, loser) distinct :- TrainingResult(winner, loser);
AnyResult(winner, loser) distinct :- TestResult(winner, loser);

# The fight whose outcome contradicts the learned strengths the most.
BiggestUpset() ArgMax= story -> shock :-
  AnyResult(winner, loser),
  story = winner ++ " defeated " ++ loser,
  shock = Strength(loser) - Strength(winner);

Test(correct: CorrectlyPredicted(), total: TotalTest(),
     champion: Champion(), underdog: Underdog(),
     upset: BiggestUpset());
