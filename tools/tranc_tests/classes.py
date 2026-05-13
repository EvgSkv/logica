class Counter:
  count: int = 0

  def increment(self) -> int:
    self.count = self.count + 1
    return self.count

  def reset(self):
    self.count = 0

  def value(self) -> int:
    return self.count

c = Counter()
print(c.value())
c.increment()
c.increment()
c.increment()
print(c.value())
c.reset()
print(c.value())
