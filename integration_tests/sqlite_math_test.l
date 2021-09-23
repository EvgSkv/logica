#
# Copyright 2021 Google LLC
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

# Testing mathematical functions in SQLite.

@Engine("sqlite");
Test(Sqrt(2));
Test(2 ^ 3);
Test(Exp(1));
Test(Log(2.7182818284 ^ 5));
Test(Sin(3.141592 / 3));
Test(Cos(3.141592 / 3));
Test(Acos(-1));
Test(Asin(1));