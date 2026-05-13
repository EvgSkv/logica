def KeyValSum(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    result = dict(a)
    for k, v in b.items():
        result[k] = result.get(k, 0) + v
    return result

x = {"apples": 3, "bananas": 2}
y = {"bananas": 5, "cherries": 1}
z = KeyValSum(x, y)
print(z)
