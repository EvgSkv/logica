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

@Engine("psql");

Kitchensync(
    name: "sync 1", 
    items: [{item: "plate", num: 10}, {item: "cup", num: 6}]);
Kitchensync(
    name: "sync 2", 
    items: [{item: "plate", num: 15}, {item: "spoon", num: 20}]);
Kitchensync(
    name: "luxury sync", 
    items: [{item: "fork", num: 5}, {item: "cup", num: 4}]);

Test(name:, overview:) :-
  Kitchensync(name:, items:),
  Kitchensync(name:, items:),
  overview List= (
    {item:, quantity:} :-
    quantity = (
        if num > 9 then
          "large"
        else
          "small"
    ),
    num > 5,
    {item:, num:} in items
  );