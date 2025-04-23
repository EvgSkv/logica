
# Win(x) :- Move(x, y), ~Win(y)

W(x, y) :- Move(x, y), Move(y, z) => W(z);
