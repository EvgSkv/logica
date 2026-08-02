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

# A non-converging counter caps at the explicit repetition count of
# @Recursive(N, 100, mode: "neural"): 100 sweeps plus the final
# Gauss-Seidel pass gives 101, exactly like the SQL diamond iteration
# with the same count.

@Engine("duckdb");

@Recursive(N, 100, mode: "neural");

N() += 1;
N() += N();

Test() += N();
