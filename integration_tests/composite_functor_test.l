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

# Test for composite functor.

Traffic(campaign: 1, cookie: 100, country: "US");
Traffic(campaign: 2, cookie: 200, country: "US");
Traffic(campaign: 3, cookie: 300, country: "US");
Traffic(campaign: 4, cookie: 400, country: "CA");
Traffic(campaign: 5, cookie: 500, country: "CA");
Traffic(campaign: 6, cookie: 600, country: "US");

# Functor of [Table] argument.
Anonymize(..r) :- Table(cookie:, ..r);

# Functor of [Table, Country] arguments.
FilterToCountry(..r) :- Table(..r), r.country == Country();

US() = "US";

# Filter to US.
@Make(TrafficUS, FilterToCountry, {Table: Traffic, Country: US});
@NoInject(TrafficUS);  # We want to use ..r.

# Anonymize.
@Make(AnonymizedTrafficUS, Anonymize, {Table: TrafficUS});

# Just anonymize traffic. (for test debugging)
@Make(AnonymizedTraffic, Anonymize, {Table: Traffic});
