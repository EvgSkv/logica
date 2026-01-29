@Engine("clickhouse");

Items(item: "Soap", price: 20);
Items(item: "Milk", price: 10);
Items(item: "Bread", price: 5);
Items(item: "Coffee", price: 7);
Items(item: "Firewood", price: 15);

MoreExpensiveThan(item1) Array= item2 -> item2 :-
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

# ClickHouse limitation: correlated subqueries in FROM are not supported.
# We avoid `item_record in items` by re-joining BuyEvent for expensive_items.
PurchaseRaw(purchase_id:, items:, expensive_items:, buyer_id:) :-
  Buyer(buyer_id:, purchase_id:),
  items Array= (
    item -> {item:, quantity:, price:} :-
    BuyEvent(purchase_id:, item:, quantity:),
    Items(item:, price:)
  ),
  expensive_items Array= (
    {item:, more_expensive_than:} -> {item:, more_expensive_than:} :-
    BuyEvent(purchase_id:, item:),
    more_expensive_than = MoreExpensiveThan(item)
  );

# Sorting step: Order the already-materialized rows.
@OrderBy(Purchase, "purchase_id");
Purchase(purchase_id:, items:, expensive_items:, buyer_id:) :-
  PurchaseRaw(purchase_id:, items:, expensive_items:, buyer_id:);

Test(purchase_id:, items:, expensive_items:, buyer_id:) :-
  Purchase(purchase_id:, items:, expensive_items:, buyer_id:);
