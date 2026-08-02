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

# Max-flow relaxation dynamics running as a neural iteration.
# The recursive cover is {Volume, Flow}: Volume rules are vector updates,
# the Flow rule is an elementwise clipped difference over the Pipe support.
# Everything before @Recursive is plain SQL (hashes, ranges, degrees).
# The neural iteration must write back both Volume and Flow tables:
# TotalFlow and Test read them downstream as ordinary SQL.

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
NumNodes() += 1 :- Node();

@Recursive(Volume, 1000, mode: "neural");
@OrderBy(Volume, "col0");

Volume(x) += 0 :- Node(x);
Volume(x) += Volume(x);
Volume(s) += v - Volume(s) + Sum{Flow(s, x)} :- Source(s), v = NumNodes() * MaxD() * MaxCap();
Volume(t) += -1 * Sum{Flow(x, t)} :- Target(t);

Volume(x) += -1 * Flow(x, y);
Volume(y) += Flow(x, y);

Clip(under, value, over) = Greatest(under, Least(over, value));

Flow(x, y) += Clip(0, (Volume(x) - Volume(y)) / (D(x) + 1), Pipe(x, y));

TotalFlow() += Flow(x, t) :- Target(t);

ActiveFlows() += 1 :- f = Flow(x, y), f > 0.001;

Test(total: Round(TotalFlow(), 3), active: ActiveFlows());
