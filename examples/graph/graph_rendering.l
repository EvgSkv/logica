# Regular edges.
R(x, y,
  arrows: "to",
  color? Max= "rgba(40, 40, 40, 0.5)",
  dashes? Min= true, 
  width? Max= 2,
  physics? Max= false,
  smooth? Max= false) distinct :- E(x, y);
# Edges of the reduction.
R(x, y,
  arrows: "to",
  color? Max= "rgba(90, 30, 30, 1.0)",
  dashes? Min= false, 
  width? Max= 4,
  physics? Max= true,
  smooth? Max= true) distinct :- TR(x, y);