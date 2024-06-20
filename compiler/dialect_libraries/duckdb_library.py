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
`=`(left:, right:) = right :- left == right;

Arrow(left, right) = arrow :-
  left == arrow.arg,
  right == arrow.value;

PrintToConsole(message) :- 1 == SqlExpr("PrintToConsole({message})", {message:});

ArgMin(arr) = SqlExpr(
    "argmin({a}, {v})", {a:, v:}) :- Arrow(a, v) == arr;

ArgMax(arr) = SqlExpr(
    "argmax({a}, {v})", {a:, v:}) :- Arrow(a, v) == arr;

ArgMaxK(a, l) = SqlExpr(
  "(array_agg({arg} order by {value} desc))[1:{lim}]",
  {arg: a.arg, value: a.value, lim: l});

ArgMinK(a, l) = SqlExpr(
  "(array_agg({arg} order by {value}))[1:{lim}]",
  {arg: a.arg, value: a.value, lim: l});

Array(arr) =
    SqlExpr("ArgMin({v}, {a})", {a:, v:}) :- Arrow(a, v) == arr; 

RecordAsJson(r) = SqlExpr(
  "ROW_TO_JSON({r})", {r:});

Fingerprint(s) = SqlExpr("('x' || substr(md5({s}), 1, 16))::bit(64)::bigint", {s:});

ReadFile(filename) = SqlExpr("pg_read_file({filename})", {filename:});

Chr(x) = SqlExpr("Chr({x})", {x:});

Num(a) = a;
Str(a) = a;

"""
