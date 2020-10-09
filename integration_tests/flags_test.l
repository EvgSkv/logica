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

# Example of running:
# yodaql --f=a=my_value flags_test_manual.ydg testrun FlagValues

@DefineFlag("a", "default_value_for_a");
@DefineFlag("b", "default_value_for_b");
@DefineFlag("c", "default_value_for_c");
@DefineFlag("d", "default_value_for_d");
@DefineFlag("e", "default_value_for_e");
@DefineFlag("table_1", "default_value_for_table_1");
@DefineFlag("table_2", "default_value_for_table_2");

TestFlagValues(
  a: FlagValue("a"), b: FlagValue("b"), c: FlagValue("c"),
  d: "${d}", e: "${e}");

TestFlagTable(a:, b:) :- `${table_1}`(a:), `${table_2}`(b:);
