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

# PageRank as a neural iteration: the canonical converges-without-fixpoint
# program. The recursive rule is a (+, *) semiring contraction — a genuine
# sparse matrix-vector product in JAX. Iteration stops on epsilon
# stabilization; golden values are rounded.

@Engine("duckdb");

Link("a", "b");
Link("a", "c");
Link("b", "c");
Link("c", "a");
Link("c", "e");
Link("d", "c");
Link("e", "a");

Page(x) distinct :- Link(x, y);
Page(y) distinct :- Link(x, y);

Degree(x) += 1 :- Link(x, y);
NumPages() += 1 :- Page(x);

ResetProb() = 0.15;

@Recursive(PageRank, mode: "neural");

PageRank(x) += ResetProb() / NumPages() :- Page(x);
PageRank(y) += (1.0 - ResetProb()) * PageRank(x) / Degree(x) :- Link(x, y);

@OrderBy(Test, "col0");
Test(x, r) :- r = Round(PageRank(x), 4);
