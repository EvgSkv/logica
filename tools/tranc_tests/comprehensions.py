squares = [x * x for x in range(6)]
for s in squares:
  print(s)

evens = [x for x in range(10) if x % 2 == 0]
for e in evens:
  print(e)

d = {"a": 1, "b": 2, "c": 3}
doubled = {k: v * 2 for k, v in d.items()}
for k, v in doubled.items():
  print(k, v)

words = ["abc", "de", "f"]
lengths = {w: len(w) for w in words}
for k, v in lengths.items():
  print(k, v)
