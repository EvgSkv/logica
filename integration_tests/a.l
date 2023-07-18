Items(item: "Soap", price: 20);
Items(item: "Milk", price: 10);
Items(item: "Bread", price: 5);
Items(item: "Coffee", price: 7);
Items(item: "Firewood", price: 15);

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
