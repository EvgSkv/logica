#!/usr/bin/python
#
# Copyright 2026 Google LLC
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

# Aggregates.
ArgMin(arr) = SqlExpr(
    "argMin({a}, {v})", {a:, v:}) :- Arrow(a, v) == arr;

ArgMax(arr) = SqlExpr(
    "argMax({a}, {v})", {a:, v:}) :- Arrow(a, v) == arr;

# Best-effort top-k helpers using tuple sorting.
ArgMaxK(a, l) = SqlExpr(
  "arraySlice(arrayMap(x -> x.2, arrayReverseSort(groupArray(({value}, {arg})))), 1, {lim})",
  {arg: a.arg, value: a.value, lim: l});

ArgMinK(a, l) = SqlExpr(
  "arraySlice(arrayMap(x -> x.2, arraySort(groupArray(({value}, {arg})))), 1, {lim})",
  {arg: a.arg, value: a.value, lim: l});

Array(a) = SqlExpr(
  "arrayMap(x -> x.2, arraySort(groupArray(({arg}, {value}))))",
  {arg: a.arg, value: a.value});

RecordAsJson(r) = SqlExpr("toJSONString({x})", {x: r});

# Hash helpers.
Fingerprint(s) = SqlExpr("reinterpretAsInt64(cityHash64(toString({s})))", {s:});
NaturalHash(x) = Fingerprint(x);

Chr(x) = SqlExpr("char({x})", {x:});

Num(a) = a;
Str(a) = a;
"""
