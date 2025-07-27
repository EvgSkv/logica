#
# Copyright 2025 Google LLC
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


City("seattle");
City("los_angeles");
City("new_york");
City("chicago");

Distance("seattle", "los_angeles", 12);
Distance("seattle", "chicago", 18);
Distance("seattle", "new_york", 28);
Distance("los_angeles", "chicago", 20);
Distance("los_angeles", "new_york", 28);
Distance("chicago", "new_york", 8);

Distance(c2, c1, d) :- Distance(c1, c2, d);

Route(i, city) couldbe :-
  i in Range(4), City(city);
Route(0, "seattle");

Bad() cantbe :-
  i in Range(4), Count{ city :- Route(i, city) } != 1  |
  Count{ city :- Route(i, city) } != 4                 ;

Cost(c) :- c = Sum{ d :-
                    i in Range(3),
                    Route(i, x), Route(i + 1, y),
                    Distance(x, y, d) };

D() = Min{ c :- Cost(c) } shouldbe;
