import lib.closure.TransitiveClosure;

@Engine("bigquery");

Friend("Alice", "Bob");
Friend("Bob", "Carrol");
Friend("Bob", "Diana");
Friend("Diana", "Elon");

@OrderBy(FriendClosure, "col0", "col1");
FriendClosure := TransitiveClosure(R: Friend);

Test := FriendClosure();
