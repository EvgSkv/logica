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

@Engine("sqlite");

M("0", "a");
M("0", "1");
M("1", "0");
M("a", "b");
M("a", "c");
M("b", "c");
M("c", "d");
M("d", "e");

V(x) distinct :- M(a, b), x in [a,b];

D(x, n) :- V(x), n += (1 :- M(x));

Loss(x) :- D(x, n), n is null;
Loss(x) :- D(x, n), num_wins += (1 :- M(x, y), Win(y)), num_wins >= n;

@Recursive(Win);
Win(x) distinct :- M(x, y), Loss(y);

@OrderBy(Test, "col0");
Test(x -> "win") :- Win(x);
Test(x -> "loss") :- Loss(x);
Test(x -> "draw") :- V(x), ~Win(x), ~Loss(x);
