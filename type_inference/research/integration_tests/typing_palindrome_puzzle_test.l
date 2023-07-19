#!/usr/bin/python
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

@Engine("psql");

Word("abbacdcaaaxx");

Char(i) = Substr(word, i + 1, 1) :- Word(word), i in Range(Length(word));

@Ground(Palindrome);
Palindrome(i, i) = Char(i);
Palindrome(i, i + 1) = Char(i) ++ Char(i + 1) :- Char(i) == Char(i + 1);
Palindrome(i - 1, j + 1) = Char(i - 1) ++ Palindrome(i, j) ++ Char(j + 1) :- Palindrome(i, j), Char(i - 1) == Char(j + 1);

@Ground(Path);
Path(i, j) = {path: [Palindrome(i, j)]} distinct;
Path(i, k) = {path: ArrayConcat(Path(i, j).path,  Path(j + 1, k).path)} distinct;

ShortestPath() ArgMin= path -> Size(path.path) :- path == Path();

