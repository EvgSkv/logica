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

# Simple functor test.

@Engine("bigquery");

Events1(campaign: 1) :- x in [0, 0, 0];        # 3 events.
Events1(campaign: 2) :- x in [0, 0];           # 2 events.
Events1(campaign: 3) :- x in [0, 0, 0, 0, 0];  # etc.

Events2(campaign: 2) :- x in [0];
Events2(campaign: 3) :- x in [0, 0, 0, 0];
Events2(campaign: 4) :- x in [0, 0, 0, 0, 0, 0];

# Functor of [Events] argument.
Traffic(campaign:, impression_count? += 1) distinct :- Events(campaign:);

@Make(Traffic1, Traffic, {Events: Events1});
@Make(Traffic2, Traffic, {Events: Events2});

@OrderBy(Test, "col0", "campaign");
Test("traffic1", ..r) :- Traffic1(..r);
Test("traffic2", ..r) :- Traffic2(..r);

