# Example of logical recursion.
import examples.scripts.queen_victoria.Parent;

@Engine("sqlite");

Ancestor(a, b) distinct :-
  Parent(a, b) | (Ancestor(a, x), Ancestor(x, b));
