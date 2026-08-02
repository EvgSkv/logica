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

# UniformHash and NormalHash: deterministic hash-based pseudo-randoms used
# for initializing learnable predicates. The golden pins determinism; the
# statistics rows check that on a thousand samples the uniform mean is
# around 1/2 and the normal mean and variance are around 0 and 1.

@Engine("duckdb");

s(x) = ToString(x);

Sample(x) :- x in Range(1000);

UniformMean() += UniformHash("u" ++ s(x)) / 1000.0 :- Sample(x);
NormalMean() += NormalHash("n" ++ s(x)) / 1000.0 :- Sample(x);
NormalVariance() += NormalHash("n" ++ s(x)) ^ 2 / 1000.0 :- Sample(x);

@OrderBy(Test, "col0");
Test("normal_of_1", Round(NormalHash(1), 4));
Test("normal_of_a", Round(NormalHash("a"), 4));
Test("normal_mean", Round(NormalMean(), 1));
Test("normal_variance", Round(NormalVariance(), 1));
Test("uniform_of_1", Round(UniformHash(1), 4));
Test("uniform_mean", Round(UniformMean(), 1));
