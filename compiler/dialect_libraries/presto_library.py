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

ArgMin(a) = SqlExpr("(ARRAY_AGG({arg} order by {value}))[1]",
                    {arg: a.arg, value: a.value});

ArgMax(a) = SqlExpr(
  "(ARRAY_AGG({arg} order by {value} desc))[1]",
  {arg: a.arg, value: a.value});

ArgMaxK(a, l) = SqlExpr(
  "SLICE(ARRAY_AGG({arg} order by {value} desc), 1, {lim})",
  {arg: a.arg, value: a.value, lim: l});

ArgMinK(a, l) = SqlExpr(
  "SLICE(ARRAY_AGG({arg} order by {value}), 1, {lim})",
  {arg: a.arg, value: a.value, lim: l});

Array(a) = SqlExpr(
  "ARRAY_AGG({value} order by {arg})",
  {arg: a.arg, value: a.value});
"""
