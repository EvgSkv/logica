def classify(n: int) -> str:
  if n < 0:
    return "negative"
  elif n == 0:
    return "zero"
  else:
    return "positive"

print(classify(-3))
print(classify(0))
print(classify(7))

def abs_val(x: int) -> int:
  if x < 0:
    return 0 - x
  return x

print(abs_val(-42))
print(abs_val(42))
print(abs_val(0))
