#
# Copyright 2023 Google LLC
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

# What have we learned writing this test?
# Recursive errors need improvement.
# 1. If recursion fails to eliminate, it may manifest as psql type errors.
/*
@Recursive(Advantage, 5);
BestMove(x,
         target? ArgMin= y -> Advantage(y),
         value? Min= Advantage(y)) distinct :-
  E(x, y);

Advantage(x) += EndgamePrize(x);
Advantage(x) += -worst_value * 0.90 :-
  V(x),
  BestMove(x, value: worst_value);
*/

# 2. Recursion of a predicate on itself and on recursive fails to eliminate.
/*
@Recursive(BestMove, 5);
BestMove(x,
         target? ArgMin= y -> Advantage(y),
         value? Min= Advantage(y)) distinct :-
  E(x, y);

Advantage(x) += EndgamePrize(x);
Advantage(x) += -worst_value * 0.90 :-
  Advantage(Endgame()),
  V(x),
  BestMove(x, value: worst_value);
*/


@Engine("psql");

E(1, 2);
E(2, 1);
E(2, 3);
E(3, 4);
E(4, 5);
V(x) distinct :- x in [a,b], E(a,b);

Endgame() = 5;
EndgamePrize(Endgame()) = 1;

@Recursive(BestMove, 20);
@OrderBy(BestMove, "col0");
BestMove(x,
         target? ArgMin= y -> Advantage(y),
         value? Min= Advantage(y)) distinct :-
  E(x, y);

Advantage(x) += EndgamePrize(x);
Advantage(x) += 0 :- V(x);
Advantage(x) += -worst_value * 0.90 :-
  V(x),
  BestMove(x, value: worst_value);

Test := BestMove();