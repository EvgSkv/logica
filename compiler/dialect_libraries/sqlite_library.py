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

library = """
->(left:, right:) = {arg: left, value: right};

Arrow(left, right) = arrow :-
  left == arrow.arg,
  right == arrow.value;

PrintToConsole(message) :- 1 == SqlExpr("PrintToConsole({message})", {message:});

ArgMin(arr) = Element(
    SqlExpr("ArgMin({a}, {v}, 1)", {a:, v:}), 0) :- Arrow(a, v) == arr;

ArgMax(arr) = Element(
    SqlExpr("ArgMax({a}, {v}, 1)", {a:, v:}), 0) :- Arrow(a, v) == arr;

ArgMinK(arr, k) = 
    SqlExpr("ArgMin({a}, {v}, {k})", {a:, v:, k:}) :-
  Arrow(a, v) == arr;

ArgMaxK(arr, k) =
    SqlExpr("ArgMax({a}, {v}, {k})", {a:, v:, k:}) :- Arrow(a, v) == arr;

ReadFile(filename) = SqlExpr("ReadFile({filename})", {filename:});

ReadJson(filename) = ReadFile(filename);

WriteFile(filename, content:) = SqlExpr("WriteFile({filename}, {content})",
                                        {filename:, content:});
"""
