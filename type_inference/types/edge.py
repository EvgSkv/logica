import typing

from type_inference.types.expression import Expression


class Edge:
  def __init__(self, vertices: typing.Tuple[Expression, Expression], start: int, end: int):
    self.vertices = vertices
    self.start = start
    self.end = end


class Equality(Edge):
  def __init__(self, left: Expression, right: Expression, start: int, end: int):
    super().__init__((left, right), start, end)
    self.left = left
    self.right = right


class EqualityOfField(Edge):
  def __init__(self, record: Expression, field: str, value: Expression, start: int, end: int):
    super().__init__((record, value), start, end)
    self.record = record
    self.field = field
    self.value = value


class EqualityOfElement(Edge):
  def __init__(self, list: Expression, element: Expression, start: int, end: int):
    super().__init__((list, element), start, end)
    self.list = list
    self.element = element
