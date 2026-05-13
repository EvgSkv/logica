a = "hello"
b = " world"
print(a + b)

def repeat(s: str, n: int) -> str:
  result = ""
  for i in range(n):
    result = result + s
  return result

print(repeat("ab", 5))
print(repeat("x", 0))
print(repeat("!", 3))
