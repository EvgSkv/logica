from typing import Tuple

from type_inference.types.expression import Expression, SubscriptAddressing, PredicateAddressing


class Edge:
  def __init__(self, vertices: Tuple[Expression, Expression], bounds: Tuple[int, int]):
    self.vertices = vertices
    self.bounds = bounds

  def __eq__(self, other):
    return isinstance(other, type(self)) and set(self.vertices) == set(other.vertices) and self.bounds == other.bounds

  def __hash__(self):
    return hash((frozenset(self.vertices), self.bounds))


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
    super(FieldBelonging, self).__init__((parent, field), bounds)
    self.parent = parent
    self.field = field


class PredicateArgument(Edge):
  def __init__(self, logica_value: PredicateAddressing, argument: PredicateAddressing, bounds: Tuple[int, int]):
    super(PredicateArgument, self).__init__((logica_value, argument), bounds)
    self.logica_value = logica_value
    self.argument = argument
