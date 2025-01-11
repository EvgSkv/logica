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

@Engine("bigquery");

@OrderBy(Test, "col0");
Test("Tan") = Round(Tan(3.14159265 / 4.0), 3);
Test("Least") = Round(Least(Sin(0.5), Sin(0.7), Sin(0.001)), 5);
Test("Exp") = Round(Pow((1 + 2.0 / 1000000.0), 1000000) - Exp(2.0), 3)

