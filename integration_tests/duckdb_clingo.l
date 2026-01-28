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

@Engine("duckdb", clingo: true);

Models() = RunClingo("""

name(ceasar).
name(leo).
name(napoleon).

dog(1).
dog(2).

% Dog can have a name.
{dogname(D, N)} :- dog(D), name(N).

% Dog with a name is named.
nameddog(D) :- dogname(D, N).

% Every dog has a name.
:- dog(D), not nameddog(D).

% Dog has no more than 1 name.
:- dogname(D, N1), dogname(D, N2), N1 != N2.

% All dogs deserve unique name.
:- dogname(D1, N), dogname(D2, N), D1 != D2.

""");

Test(model: RenderClingoModel(m.model, " ")) :- m in Models();
