from collections import defaultdict

from type_inference.types.edge import Edge


class TypesGraph:
  def __init__(self):
    self.expression_connections = defaultdict(lambda: defaultdict(list))
    self.expression_type = dict()

  def connect(self, edge: Edge, oriented: bool = False):
    first_expression, second_expression = edge.vertices
    self.expression_connections[first_expression][second_expression].append(edge)

    if not oriented:
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
