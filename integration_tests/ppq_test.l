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

# Test for ++? operator.

@Engine("bigquery");

Character(full_name: "Toby the dog");
Character(full_name: "Pete the cat");
Character(full_name: "Sharik the dog");

@OrderBy(Dog, "name");
Dog(name:) :- Character(full_name: name ++? " the dog");
Dog(name: short_name ++? " the musketeer") :- short_name in [
  "Atos", "Portos", "Aramis"];
