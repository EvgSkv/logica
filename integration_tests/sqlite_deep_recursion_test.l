#
# Copyright 2020 Google LLC
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

# Test for Element function in SQLite.

@Engine("sqlite");

S() = 0;

@Recursive(N, 1000);
N() = S();
N() = N() + 1;

@Recursive(N30, 30);
N30() = 0;
N30() = N30() + 1;

@Recursive(N29, 29);
N29() = 0;
N29() = N29() + 1;

SM() = 100;
M := N(S: SM);

@OrderBy(Test, "col0");
Test("M") Max= M();
Test("N") Max= N();
Test("N30") Max= N30();
Test("N29") Max= N29();
