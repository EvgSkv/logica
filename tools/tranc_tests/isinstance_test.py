x = {"a": 1, "b": 2}
y = [1, 2, 3]
z = "hello"
w = 42
s = {1, 2, 3}

if isinstance(x, dict):
  print("x is dict")
else:
  print("x is not dict")

if isinstance(y, list):
  print("y is list")

if isinstance(z, str):
  print("z is str")

if isinstance(w, int):
  print("w is int")

if isinstance(s, set):
  print("s is set")

if isinstance(x, list):
  print("WRONG")
else:
  print("x is not list")

if isinstance(y, (list, dict)):
  print("y is list or dict")

if isinstance(z, (int, float)):
  print("WRONG")
else:
  print("z is not numeric")
