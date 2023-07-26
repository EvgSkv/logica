#!/usr/bin/python
#
# Copyright 2023 Google LLC
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

@Engine("sqlite");

Weight("John") = 100;
Weight("Mary") = 50;

FoodToCalories(person) = personal_map :-
  base_map == [
    "apple" -> 60,
    "banana" -> 100,
    "orange" -> 80,
    "bread" -> 200
  ],
  personal_map List= (
    item -> calories * Weight(person) / 100.0 :-
    item -> calories in base_map
  );

Purchase(person: "John", food: ["apple", "bread"]);
Purchase(person: "Mary", food: ["orange", "banana", "apple"]);

CaloriesPurchased(person) += calories :-
  Purchase(person:, food:),
  item in food,
  item -> calories in FoodToCalories(person);

