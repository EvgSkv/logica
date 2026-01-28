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

# Testing a long sequence of Make statements.

@Engine("bigquery");

S("success");

R(x) :- T(x);

@Make(F1, R, {T: T1});
@Make(F2, F1, {T1: T2});
@Make(F3, F2, {T2: T3});
@Make(F4, F3, {T3: T4});
@Make(F5, F4, {T4: T5});
@Make(F6, F5, {T5: T6});
@Make(F7, F6, {T6: S});
