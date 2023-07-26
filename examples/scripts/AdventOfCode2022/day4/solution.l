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

# Solution to AdventOfCode 2022, Day 4.
# https://adventofcode.com/2022/day/4

@Engine("sqlite");
NewLine() = SqlExpr("char(10)", {});
Data() = ReadFile("input.txt");


ParseInterval(s) = {start: ToInt64(a),
                    end: ToInt64(b)} :-
  parts == Split(s, "-"),
  a == Element(parts, 0),
  b == Element(parts, 1);

@Ground(PairOfTasks);
PairOfTasks(task1, task2) :-
  line in Split(ReadFile("input.txt"), NewLine()),
  line != "",
  task_strs == Split(line, ","),
  task1 == ParseInterval(Element(task_strs, 0)),
  task2 == ParseInterval(Element(task_strs, 1));

Overlap(i1, i2) = {start: Greatest(i1.start, i2.start),
                   end: Least(i1.end, i2.end)};

OneContainsTheOther(i1, i2) :-
  o == Overlap(i1, i2),
  l1 == i1.end - i1.start,
  l2 == i2.end - i2.start,
  o.end - o.start == Least(l1, l2);

NumMatreshkas() += 1 :-
  PairOfTasks(i1, i2),
  OneContainsTheOther(i1, i2);

NumOverlapping() += 1 :-
  PairOfTasks(i1, i2),
  Overlap(i1, i2) == o,
  o.end - o.start >= 0;
