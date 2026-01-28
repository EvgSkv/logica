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

@Engine("duckdb", clingo: {time_limit: ∞, models_limit: ∞});

Hamlet("to be") couldbe;
Hamlet("not to be") couldbe;
Hamlet("is") :- Hamlet(x);
Ophelia("is") couldbe;

OpheliaHappy() :- Ophelia("is"), Hamlet("is"), Hamlet("to be"), ~Hamlet("not to be");

OpheliaUnhappy() cantbe :- ~OpheliaHappy();

HamletStory() = ["Hamlet", "Ophelia", "OpheliaHappy", "OpheliaUnhappy"];

Test() = RenderClingoModel(m.model, ",") :- m in Clingo(HamletStory(), []);