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

# Testing that disjunction works via solving a puzzle.
# Traveler asked four aborigines and got these answers:
# A: Yesterday was Wednesday.
# B: Tomorrow will be Sunday.
# C: Today is Friday.
# D: The day before yesterday was Thursday.
# Because everything you need to know is how many people lied, I will not tell.
# What day of the week was it?
# Source: http://brainden.com/logic-problems.htm

# Note that we can not factor out the logic of (x == "T" | ....) into a helper
# function because disjunction is supported only for all-out predicates.
@OrderBy(Options, "col0");
Options(day, a, b, c, d) :-
  day in [0, 1, 2, 3, 4, 5, 6],
  ((a == "T", Mod(day + 6, 7) == 3) | (a == "F", Mod(day + 6, 7) != 3)),
  ((b == "T", Mod(day + 1, 7) == 0) | (b == "F", Mod(day + 1, 7) != 0)),
  ((c == "T", day == 5) | (c == "F" , day != 5)),
  ((d == "T", Mod(day + 5, 7) == 4) | (d == "F", Mod(day + 5, 7) != 4));

Liar(x) = ToInt64(x == "F");

NumLiarsByDay(day) = Liar(a) + Liar(b) + Liar(c) + Liar(d) :-
  Options(day, a, b, c, d);

NumDaysByLiarNumber(NumLiarsByDay(day)) Count= day;

NumLiarsIdentifyingDay() = x :- NumDaysByLiarNumber(x) == 1;

Answer(anwser: day_name) :-
  NumLiarsByDay(day) == NumLiarsIdentifyingDay(),
  day_name == Element(["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday",
                       "Friday", "Saturday"], day);
