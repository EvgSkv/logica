from collections import defaultdict

from parser_py.parse import HeritageAwareString
from type_inference.types.edge import Edge
from type_inference.types.expression import Literal, Variable


def _to_dict(obj, ignore_keys=None):
  if isinstance(obj, HeritageAwareString):
    return str(obj)

  if isinstance(obj, Literal):
    return type(obj).__name__

  if not hasattr(obj, "__dict__"):
    return obj

  result = obj.__dict__
  return {k: _to_dict(v, ignore_keys) for k, v in result.items() if not ignore_keys or k not in ignore_keys}


class TypesGraph:
  def __init__(self):
    self.expression_connections = defaultdict(lambda: defaultdict(list))

  def connect(self, edge: Edge):
    first_expression, second_expression = edge.vertices
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

  @property
  def head_defined(self):
    return (k for k in self.expression_connections.keys() if isinstance(k, Variable))

  def to_serializable_edges_list(self):
    return [_to_dict(e, ("vertices",)) for e in self.to_edges_list()]

  def to_edges_list(self):
    return {edge for i in self.expression_connections.values() for edges in i.values() for edge in edges}
