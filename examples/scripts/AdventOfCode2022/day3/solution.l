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
NewLine() = SqlExpr("char(10)", {});
Data() = ReadFile("input.txt");

@Ground(Rucksack);
Rucksack(x, g) :-
  lines == Split(Data(), NewLine()),
  i in Range(Size(lines)),
  x == Element(lines, i),
  g == i / 3,  # In SQLite division is integer.
  x!= "";

RucksackItem(item, x, half) distinct :-
  Rucksack(x),
  i in Range(Length(x)),
  item == Substr(x, i + 1, 1),
  half == (
    if i < Length(x) / 2 then
      "left"
    else
      "right"
  );

MisplacedItem() = item :-
  RucksackItem(item, x, "left"),
  RucksackItem(item, x, "right");

ItemPriority(item) = priority :-
  i in Range(26),
  priority == i + 1,
  item == SqlExpr("char({c})", {c: i + 97});  # Starting from 'a'.
ItemPriority(item) = priority :-
  i in Range(26),
  priority == i + 27,
  item == SqlExpr("char({c})", {c: i + 65});  # Starting from 'A'.

TotalPriorityOfMisplacedItems() += ItemPriority(MisplacedItem());

ItemRucksackCountPerGroup(item, g) Count= x :-
  Rucksack(x, g),
  RucksackItem(item, x);

@OrderBy(Badge, "col0");
Badge(g) = item :- ItemRucksackCountPerGroup(item, g) == 3;

BadgesPriority() += ItemPriority(Badge());
