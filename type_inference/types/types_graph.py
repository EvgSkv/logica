from collections import defaultdict

from type_inference.types.edge import Edge, Equality, EqualityOfField, EqualityOfElement


def _get_expressions(edge: Edge):
  if isinstance(edge, Equality):
    return edge.left, edge.right

  if isinstance(edge, EqualityOfField):
    return edge.record, edge.value

  if isinstance(edge, EqualityOfElement):
    return edge.list, edge.element


class TypesGraph:
  def __init__(self):
    self.expression_connections = defaultdict(lambda: defaultdict(list))
    self.expression_type = dict()

  def connect(self, edge: Edge):
    first_expression, second_expression = _get_expressions(edge)

    self.expression_connections[first_expression][second_expression].append(edge)
    self.expression_connections[second_expression][first_expression].append(edge)

  def __or__(self, other):
    if not isinstance(other, TypesGraph):
      raise TypeError("unsupported operation - both must be of type TypesGraph")

    result = TypesGraph()
    result.expression_connections = self.expression_connections

    for key1, subdict in other.expression_connections.items():
      for key2, value in subdict.items():
        result.expression_connections[key1][key2].extend(value)

    return result

