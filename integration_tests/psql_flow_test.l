#
# Copyright 2024 Google LLC
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

# E(i, i + 1) = 1 :- i in Range(3);

RandInt(s, n) = Abs(Fingerprint(s)) % n;

E(0, 1) = 3;
E(1, 2) = 10;
E(2, 3) = 3;
E(0, 4) = 10;
E(4, 2) = 10;
E(1, 5) = 10;
E(5, 3) = 10;

G(i, j) += e  :- e = E(i, j) | e = E(j, i);

S() = 0;
T() = 3;
 
V() = x distinct :- x in [i, j], G(i, j);

@Ground(Flow);
@Ground(Capacity);
@Ground(G);
@Ground(Opportunity);
@Ground(ActivePath);
@OrderBy(Test, "col0", "col1");
@Recursive(Flow, 20);

Flow(i, j) += 0 :- G(i, j);

Capacity(0, 0) = 0 :- 1 = 0;
Capacity(i, j) = G(i, j) - Flow(i, j) + Flow(j, i);

Leak() = 0.001;

Opportunity(S(), path? ArgMax= l -> 100) Max= 100 :-
    l ~ [{x: Num, y: Num}], l = [];

Opportunity(y, path? ArgMax= (path ++ [{x:, y:}]) -> v ) Max= v :-
    v = Least(Opportunity(x, path:), Capacity(x, y)) - Leak(),
    ~ActivePath();

ActivePath() = {path: [{x:0, y: 0}], v: 0} :- 1 = 0;
ActivePath() = {path:, v:} :- Opportunity(T(), path:) = v, v > 0;

Flow(i, j) += Flow(i, j);
Flow(i, j) += v :-
    {path:, v:} = ActivePath(),
    v > 0,
    e in path,
    i = e.x, j = e.y,
    Constraint(!~ Opportunity(T()));

FlowVis(i, j, arrows: "none", width: e, physics: false, color: "#eee") distinct :-
    G(i, j) = e, i < j, Flow(i, j) < 0.5, Flow(j, i) < 0.5;
FlowVis(i, j, arrows: "to", width: f, physics: true, color: "#444") distinct :-
    Flow(i, j) = f, f > 0;

TotalFlow() += Flow(x, T());

Test(i, j) = Flow(i, j);