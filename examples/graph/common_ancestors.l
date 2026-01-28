# Use unbounded depth (-1) to find ancestors.
@Recursive(E, -1, stop: FoundCommonAncestor);
E(x, item,
  TaxonLabel(x), TaxonLabel(item)) distinct :-
  SuperTaxon(item,x),
  ItemOfInterest(item) | E(item);
NumRoots() += 1 :- E(x,y), ~E(z,x);
# Stop when common ancestor is found.
FoundCommonAncestor() :- NumRoots() = 1;