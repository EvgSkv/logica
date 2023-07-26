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

StoreItem(name: "apple", price: 2.0);
StoreItem(name: "banana", price: 1.0);
StoreItem(name: "orange", price: 1.5);
StoreItem(name: "pear", price: 3.0);

PercentageDiscout(item_name: "apple", percentage: 10);
PercentageDiscout(item_name: "orange", percentage: 20);

CustomerPurchase(customer_name: "John", item_name: "apple", quantity: 2);
CustomerPurchase(customer_name: "John", item_name: "banana", quantity: 1);
CustomerPurchase(customer_name: "John", item_name: "orange", quantity: 3);
CustomerPurchase(customer_name: "John", item_name: "orange", quantity: 3);
CustomerPurchase(customer_name: "Jane", item_name: "pear", quantity: 1);
CustomerPurchase(customer_name: "Jane", item_name: "banana", quantity: 2);
CustomerPurchase(customer_name: "Jane", item_name: "apple", quantity: 2);

@OrderBy(CustomerSavings, "customer_name");
CustomerSavings(customer_name:,
                total_savings? += savings,
                max_fraction? Max= (fraction_savings = percentage / 100.0)) distinct :-
  CustomerPurchase(customer_name:, item_name:, quantity:),
  PercentageDiscout(item_name:),
  StoreItem(name: item_name, price:),
  PercentageDiscout(item_name:, percentage:),
  savings = price * fraction_savings * quantity;

Test := CustomerSavings();