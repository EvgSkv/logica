def outer(x: int) -> int:
  def inner(y: int) -> int:
    return x + y
  return inner(10)

print(outer(32))
print(outer(0))
print(outer(-5))

def make_adder(n: int) -> int:
  def adder(x: int) -> int:
    return x + n
  return adder(100)

print(make_adder(7))
