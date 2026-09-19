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

# The max-flow relaxation in its natural pair-keyed form, written
# without combines: every rule rides static rows, so Flow lives as
# a vector over the support of Pipe and the dense node-by-node
# tensor is never built. The sibling neural_flow test keeps the
# combine style and runs dense; both must agree with the SQL
# engine and with each other.

@Engine("duckdb");

s(x) = ToString(x);

@OrderBy(E, "col0", "col1");
E(a, b) += 1 :-
  i in Range(60),
  a = NaturalHash("a" ++ s(i)) % 30,
  b = (a + 1 + NaturalHash("b" ++ s(i)) % 5),
  b < 30,
  b != 13;
Source(3);
Target(28);

Pipe(x, y) += E(x, y);
Pipe(x, y) += E(y, x);

Cap(x) += Pipe(x);
D(x) += 1 :- Pipe(x);

MaxD() Max= D();
MaxCap() Max= Cap();

Node(x) distinct :- Pipe(x);
NumNodes() += 1 :- Node(x);

@Recursive(Volume, 1000, mode: "neural");
@OrderBy(Volume, "col0");

Volume(x) += 0 :- Node(x);
Volume(x) += Volume(x);

OutFlow(x) += 0.0 :- Node(x);
OutFlow(x) += Flow(x, y);
InFlow(x) += 0.0 :- Node(x);
InFlow(y) += Flow(x, y);

Volume(s) += v - Volume(s) + OutFlow(s) :- Source(s), v = NumNodes() * MaxD() * MaxCap();
Volume(t) += -1 * InFlow(t) :- Target(t);

Volume(x) += -1 * Flow(x, y);
Volume(y) += Flow(x, y);

Clip(under, value, over) = Greatest(under, Least(over, value));

Flow(x, y) += Clip(0, (Volume(x) - Volume(y)) / (D(x) + 1), Pipe(x, y));

TotalFlow() += Flow(x, t) :- Target(t);

ActiveFlows() += 1 :- f = Flow(x, y), f > 0.001;

Test(total: Round(TotalFlow(), 3), active: ActiveFlows());
