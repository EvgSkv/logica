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

# Tests for running canada.ydg on PostgreSQL.
import integration_tests.import_tests.canada.ImportedEngineer;
import integration_tests.import_tests.canada.Consume;
import integration_tests.import_tests.canada.ImportCost;
import integration_tests.import_tests.canada.DomesticCost;

@Engine("psql");

TestImportFraction() =
    Format("%.3f", import_cost / (import_cost + domestic_cost)) :-
  import_cost == ImportCost(), domestic_cost == DomesticCost();

@OrderBy(TestConsume, "col0");
TestConsume(..r) :- Consume(..r);

TestImportedEngineer(name:) :- ImportedEngineer(name:);
