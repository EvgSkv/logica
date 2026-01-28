#
# Copyright 2025 Google LLC
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

# Testing propositional implication.

Bird("duck");
Bird("sparrow");

Animal("dog");

Dragon("wyvern");

Flies("duck");
Flies("sparrow");
Flies("wyvern");

WhoFiles("animal") :- Animal(x) => Flies(x);
WhoFiles("bird") :- Bird(x) => Flies(x);
WhoFiles("dragon") :- Dragon(x) => Flies(x);

@OrderBy(Test, "col0");
Test(x) :- WhoFiles(x);
