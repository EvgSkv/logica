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

# Testing implication and OrderBy annotation.

@Engine("bigquery");

N(n1 + n2 * 5 + n3 * 25) :- l == [0,1,2,3,4], n1 in l, n2 in l, n3 in l;

Qualify(n) = (
  if n > 50 then
    "large"
  else if n > 10 then
    "medium"
  else
    "small");

@OrderBy(Qualified, "n");  # in case user wants to print it.
Qualified(n:, quality: Qualify(n)) :- N(n);

@OrderBy(QualifiedSummary, "quality");
QualifiedSummary(quality:, range_begin? Min= n, range_end? Max= n) distinct :-
  Qualified(n:, quality:);
