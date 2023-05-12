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
Purchase(customer: "John", items: [{item_name: "Eggs", price: 2.99},
                                   {item_name: "Milk", price: 3.99}]);
Purchase(customer: "Jane", items: [{item_name: "Bread", price: 4.99}, 
                                   {item_name: "Butter", price: 1.99}]);
Purchase(customer: "John", items: [{item_name: "Soda", price: 1.99}]);
Purchase(customer: "Jane", items: [{item_name: "Chips", price: 2.99}, 
                                   {item_name: "Salsa", price: 3.99}]);

CustomerInfo(customer:, 
             items? Set= item_name, 
             spend? += price) distinct :-
  Purchase(customer:, items:),
  {item_name:, price:} in items;
