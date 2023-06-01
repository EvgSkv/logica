from type_inference.types.edge import Edge
from type_inference.types.variable_types import Type


class Logger:
  def __init__(self):
    self._not_found_tables = []
    self._edges = []

  def not_found_table(self, table_name: str):
    self._not_found_tables.append(table_name)

  def types_not_match(self, edge: Edge, left_type: Type, right_type: Type):
    self._edges.append((edge, left_type, right_type))
