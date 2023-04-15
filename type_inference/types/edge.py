import typing

from type_inference.types.expression import Expression


class Equality:
  def __init__(self, left: Expression, right: Expression):
    self.left = left
    self.right = right


class EqualityOfField:
  def __init__(self, record: Expression, field: str, value: Expression):
    self.record = record
    self.field = field
    self.value = value


class EqualityOfElement:
  def __init__(self, list: Expression, element: Expression):
    self.list = list
    self.element = element


Edge = typing.TypeVar("Edge", Equality, EqualityOfField, EqualityOfElement)


class ContextEnrichedEdge(Edge):
  def __init__(self, edge: Edge, start: int, end: int):
    self.edge = edge
    self.start = start
    self.end = end
