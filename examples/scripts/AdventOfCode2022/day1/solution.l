#!/usr/bin/python
#
# Copyright 2022 Google LLC
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

@Ground(Text);
Text() = ReadFile("input.txt");

NewLine() = SqlExpr("char(10)", {});
TwoNewLines() = NewLine() ++ NewLine();

PerElfText() = x :-
  x in Split(Text(), TwoNewLines());

PerElfCalories(calories_list) :-
  per_elf_text == PerElfText(),
  calories_list List= (
    ToInt64(x) :- x in Split(per_elf_text, NewLine()));

TotalCaloriesPerElf() = elfs_total_calories :-
  PerElfCalories(calories_list),
  elfs_total_calories += (c :- c in calories_list);

# Answer to problem 1.
MaximalCalories() Max= TotalCaloriesPerElf();

ArgMax3(x) = ArgMaxK(x, 3);
Top3() ArgMax3= c -> c :- c == TotalCaloriesPerElf();

# Answer to problem 2.
TotalAmongTop3() += c :- c in Top3();
