from typing import Tuple

from type_inference.types.expression import Expression, SubscriptAddressing


class Edge:
  def __init__(self, vertices: Tuple[Expression, Expression], bounds: Tuple[int, int]):
    self.vertices = vertices
    self.bounds = bounds


class Equality(Edge):
  def __init__(self, left: Expression, right: Expression, bounds: Tuple[int, int]):
    super().__init__((left, right), bounds)
    self.left = left
    self.right = right


class EqualityOfElement(Edge):
  def __init__(self, list: Expression, element: Expression, bounds: Tuple[int, int]):
    super().__init__((list, element), bounds)
    self.list = list
    self.element = element

class FieldBelonging(Edge):
  def __init__(self, parent: Expression, field: SubscriptAddressing, bounds: Tuple[int, int]):
    super().__init__((parent, field), bounds)
    self.parent = parent
    self.field = field
