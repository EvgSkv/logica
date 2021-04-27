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

# Testing very basic syntax.

@Engine("presto", server: "localhost:8090");

Numbers(x) :- x in Range(10);
Squares(x * x) :- Numbers(x);
Cubes(x * x * x) :- Numbers(x);

Powers("some" ++ "powers", x, [1,2,3],
       odds_evens: null) :-
  Numbers(x) | Squares(x) | Cubes(x);

# Unfortunately this type of correlated subquery is not supported in
# Presto.
OddsEvens(offset) = odds_evens :-
  offset in [1,2,3,4],
  odds_evens List= (if (x + offset) % 2 == 0 then "even" else "odd" :-
                    x in Range(10));

@OrderBy(MysticPowers, "col0");
MysticPowers("powers of " ++ ToString(x),
             "half of " ++ ToString(x) ++ " is " ++ ToString(x * ToFloat64("0.5")),
             ToInt64(ToString(x)),
             odds_evens:) :-
  (Numbers(x) | Squares(x) | Cubes(x)),
  odds_evens List= (if (z + x) % 2 == 0 then "even" else "odd" :-
                    z in Range(5));

@OrderBy(Test, "col1");
Test := Powers();
