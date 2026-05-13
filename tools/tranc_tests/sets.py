a = {1, 2, 3}
b = {3, 4, 5}

print(len(a))

a.add(10)
print(10 in a)

c = a | b
print(sorted(c))

d = a & b
print(sorted(d))

e = a - b
print(sorted(e))

print(b <= a)
print({3} <= a)

a |= {20, 30}
print(20 in a)
print(30 in a)

f = set()
f.add(1)
f.add(2)
f.discard(1)
print(sorted(f))

g = set([5, 6, 7])
print(sorted(g))
