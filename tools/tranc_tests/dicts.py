d = {"a": 1, "b": 2, "c": 3}
print(d["a"])
print(d["b"])

d["d"] = 4
print(d["d"])
print(len(d))

for k, v in d.items():
  print(k, v)

if "a" in d:
  print("yes")
if "q" in d:
  print("oops")

del d["c"]
print(len(d))
