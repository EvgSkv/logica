# Testing recursion with Postgres engine.

@Engine("psql");

Edge(1, 2);
Edge(2, 3);
Edge(3, 4);
Edge(4, 5);

Edge(6, 7);
Edge(7, 8);

Edge(9, 10);
Edge(10, 11);
Edge(9, 11);

@OrderBy(Distance, "col0", "col1");
@Recursive(Distance, 5);
Distance(a, b) Min= 1 :- Edge(a, b);

Distance(a, a) Min= 0 :- Distance(a);
Distance(a, b) Min= Distance(b, a);
Distance(a, b) Min= Distance(a, c) + Distance(c, b);

@OrderBy(ComponentOf, "col0");
ComponentOf(x) Min= y :- Distance(x, y);

@OrderBy(Analyzed, "vertex");
Analyzed(vertex: x, component: ComponentOf(x), distances? List= [y, Distance(x, y)]) distinct;

Test := Analyzed();

