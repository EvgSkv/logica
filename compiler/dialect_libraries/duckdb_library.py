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
  "(array_agg({arg_1} order by {value_1} desc))[1:{lim}]",
  {arg_1: a.arg, value_1: a.value, lim: l});

ArgMinK(a, l) = SqlExpr(
  "(array_agg({arg_1} order by {value_1}))[1:{lim}]",
  {arg_1: a.arg, value_1: a.value, lim: l});

Array(a) = SqlExpr(
  "ARRAY_AGG({value} order by {arg})",
  {arg: a.arg, value: a.value});

RecordAsJson(r) = SqlExpr(
  "ROW_TO_JSON({r})", {r:});

Fingerprint(s) = NaturalHash(s);

ReadFile(filename) = SqlExpr("pg_read_file({filename})", {filename:});

Chr(x) = SqlExpr("Chr({x})", {x:});

Num(a) = a;
Str(a) = a;

Epoch(a) = epoch :-
  epoch = SqlExpr("epoch_ns({a})", {a:}) / 1000000000,
  a ~ Time, 
  epoch ~ Num;
TimeDiffSeconds(a, b) = Epoch(SqlExpr("{a} - {b}", {a:, b:}));
ToTime(a) = SqlExpr("cast({a} as timestamp)", {a:});

NaturalHash(x) = ToInt64(SqlExpr("hash(cast({x} as string)) // cast(2 as ubigint)", {x:}));

# This is unsafe to use because due to the way Logica compiles this number
# will be unique for each use of the variable, which can be a pain to debug.
# It is OK to use it as long as you undertand and are OK with the difficulty.
UnsafeToUseUniqueNumber() = SqlExpr("nextval('eternal_logical_sequence')", {});

"""
