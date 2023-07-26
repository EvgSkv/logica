#!/usr/bin/python
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

@Engine("sqlite");

NewLine() = SqlExpr("char(10)", {});

Data() = ReadFile("input.txt");

@Ground(Line);
Line() = line :-
  line in Split(Data(), NewLine()),
  line != "";

Decrypt("A") = "Rock";
Decrypt("B") = "Paper";
Decrypt("C") = "Scissors";
Decrypt("X") = "Rock";
Decrypt("Y") = "Paper";
Decrypt("Z") = "Scissors";

ItemScore("Rock") = 1;
ItemScore("Paper") = 2;
ItemScore("Scissors") = 3;

Item(x) :- ItemScore(x);

Dominates("Rock", "Scissors");
Dominates("Scissors", "Paper");
Dominates("Paper", "Rock");

# BattleResult(x, y) is result for the first player who chose x vs player who
# chose y. It is -1 for loss, 0 for draw and 1 for victory.
BattleResult(x, y) = -1 :- Dominates(y, x);
BattleResult(x, x) = 0 :- Item(x);
BattleResult(x, y) = 1 :- Dominates(x, y);

FullBattleResult(x, y) = 3 + 3 * BattleResult(x, y) + ItemScore(x);

EncryptedTournament(a, b) :-
  a == Element(actions, 0),
  b == Element(actions, 1),
  actions == Split(Line(), " ");

TournamentResult(a, b) = FullBattleResult(Decrypt(b), Decrypt(a)) :-
  EncryptedTournament(a, b);

TotalScore() += TournamentResult();

# Problem 2.

DesiredResult("X") = -1;
DesiredResult("Y") = 0;
DesiredResult("Z") = 1;

WhatToDo(opponent_action, desired_result) = your_action :-
  BattleResult(your_action, opponent_action) == desired_result;

TournamentResult2(a, b) = FullBattleResult(WhatToDo(opponent_action,
                                                    DesiredResult(instruction)),
                                           opponent_action) :-
  EncryptedTournament(a, b),
  opponent_action == Decrypt(a),
  instruction == b;

TotalScore2() += TournamentResult2();
