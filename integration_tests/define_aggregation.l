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

# Testing custom aggregation functions.

@Engine("bigquery");

SampledVisit(campaign:"1", person:123);
SampledVisit(campaign:"1", person:125);
SampledVisit(campaign:"2", person:155);
SampledVisit(campaign:"2", person:163);

CountSampled(x) = Count(ToInt64(Floor(x / 10))) * 10;

@OrderBy(SampledPeople, "campaign");
SampledPeople(campaign:,
              people? CountSampled= person) distinct :-
  SampledVisit(campaign:, person:);
