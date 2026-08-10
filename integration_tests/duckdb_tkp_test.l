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

# TKP (top-k proofs) extension test: exact path probabilities on a
# double-diamond graph. Install the extension first:
#   python3 logica.py examples/extensions/tkp.py install_extension
#
# The graph: a->b->c->d->e with detours a->g->c and c->f->e; every
# edge holds with probability 0.5. Both a->c legs and both c->e legs
# are independent diamonds, so exactly:
#   P(a->c) = 2/4 - 1/16 = 0.4375
#   P(a->e) = P(a->c) * P(c->e) = 0.4375^2 = 0.19140625
# T4P keeps all four proofs of a->e, so the truncated probability is
# the exact one.

import examples.extensions.tkp.MakeFact;
import examples.extensions.tkp.ProbConjunction;
import examples.extensions.tkp.TKP;
import examples.extensions.tkp.TkpProbability;

@Engine("duckdb");

PotentialEdge("a", "b"); PotentialEdge("b", "c");
PotentialEdge("a", "g"); PotentialEdge("g", "c");
PotentialEdge("c", "d"); PotentialEdge("d", "e");
PotentialEdge("c", "f"); PotentialEdge("f", "e");

EdgeProb(a, b) = 0.5 :- PotentialEdge(a, b);

Edge(a, b) = MakeFact(predicate: "Edge", args: [a, b],
                      probability: EdgeProb(a, b)) :- PotentialEdge(a, b);

T4P(x) = TKP(x, 4);

@Recursive(Path, 10);
Path(x, y) T4P= Edge(x, y);
Path(x, z) T4P= ProbConjunction(Path(x, y), Path(y, z));

@OrderBy(Test, "col0");
Test(y, p: Round(TkpProbability(Path("a", y)), 8)) :- Path("a", y);
