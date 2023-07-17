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

Items(item: "Soap", price: 20);
Items(item: "Milk", price: 10);
Items(item: "Bread", price: 5);
Items(item: "Coffee", price: 7);
Items(item: "Firewood", price: 15);

MoreExpensiveThan(item1) List= item2 :-
  Items(item: item1, price: price1),
  Items(item: item2, price: price2),
  price1 > price2;

BuyEvent(purchase_id: 1, item: "Soap", quantity: 3);
BuyEvent(purchase_id: 2, item: "Milk", quantity: 1);
BuyEvent(purchase_id: 3, item: "Bread", quantity: 2);
BuyEvent(purchase_id: 3, item: "Coffee", quantity: 1);
BuyEvent(purchase_id: 4, item: "Firewood", quantity: 5);
BuyEvent(purchase_id: 4, item: "Soap", quantity: 1);
BuyEvent(purchase_id: 5, item: "Milk", quantity: 4);
BuyEvent(purchase_id: 5, item: "Bread", quantity: 1);
BuyEvent(purchase_id: 5, item: "Coffee", quantity: 2);
BuyEvent(purchase_id: 6, item: "Firewood", quantity: 1);
BuyEvent(purchase_id: 6, item: "Soap", quantity: 3);
BuyEvent(purchase_id: 7, item: "Milk", quantity: 1);
BuyEvent(purchase_id: 7, item: "Bread", quantity: 2);
BuyEvent(purchase_id: 7, item: "Coffee", quantity: 1);
BuyEvent(purchase_id: 8, item: "Firewood", quantity: 5);
BuyEvent(purchase_id: 8, item: "Soap", quantity: 1);

Buyer(buyer_id: 11, purchase_id: 1);
Buyer(buyer_id: 12, purchase_id: 2);
Buyer(buyer_id: 13, purchase_id: 3);
Buyer(buyer_id: 14, purchase_id: 4);
Buyer(buyer_id: 12, purchase_id: 5);
Buyer(buyer_id: 13, purchase_id: 6);
Buyer(buyer_id: 14, purchase_id: 7);
Buyer(buyer_id: 11, purchase_id: 8);

@OrderBy(Purchase, "purchase_id");
Purchase(purchase_id:, items? List= x, buyer_id:) distinct :-
  Buyer(buyer_id:, purchase_id:),
  x = {item: item_name, quantity:, price:},
  BuyEvent(purchase_id:, item: item_name, quantity:),
  Items(item: item_name, price:);

@OrderBy(Test, "buyer_id");
Test(buyer_id:, purchases:) :-
  buyers Set= (b :- Buyer(buyer_id: b)),
  buyer_id in buyers,
  purchases List= (
    {purchase: items} :-
    Purchase(items:, buyer_id:)
  );
