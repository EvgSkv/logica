def factorial(n: int) -> int:
  if n <= 1:
    return 1
  return n * factorial(n - 1)

print(factorial(0))
print(factorial(1))
print(factorial(5))
print(factorial(10))

def fib(n: int) -> int:
  a = 0
  b = 1
  for i in range(n):
    c = a + b
    a = b
    b = c
  return a

for i in range(10):
  print(fib(i))
