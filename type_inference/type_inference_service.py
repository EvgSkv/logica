from collections import defaultdict
from typing import Set, cast

from type_inference.type_inference_exception import TypeInferenceException
from type_inference.types import edge, expression
from type_inference.types import variable_types
from type_inference.types.types_graph import TypesGraph, get_variables

literal_to_type = {expression.NumberLiteral(): variable_types.NumberType(),
                   expression.StringLiteral(): variable_types.StringType()}

inferred_rules = defaultdict(dict)
number_type = variable_types.NumberType()
string_type = variable_types.StringType()

inferred_rules['Range']['col0'] = number_type
inferred_rules['Range']['logica_value'] = variable_types.ListType(number_type)

inferred_rules['Num']['col0'] = number_type
inferred_rules['Num']['logica_value'] = number_type

inferred_rules['Str']['col0'] = string_type
inferred_rules['Str']['logica_value'] = string_type


class TypeInferenceService:
  def __init__(self, graphs: dict):
    self.graphs = graphs

  def infer_type(self, rule: str):
    variables = get_variables(rule)
    for variable in variables:
      if rule in self.graphs:
        var_type = self._infer_type(variable, set(), self.graphs[rule])
      else:
        var_type = variable_types.AnyType()
      inferred_rules[rule][variable.variable_name] = var_type
    return inferred_rules

  def _infer_type(self, expr: expression.Expression, visited: Set, graph: TypesGraph):
    if isinstance(expr, expression.Literal):
      return literal_to_type[expr]

    if isinstance(expr, expression.PredicateAddressing):
      if expr.predicate_name in inferred_rules:
        return inferred_rules[expr.predicate_name][expr.field]
      self.infer_type(expr.predicate_name)
      return inferred_rules[expr.predicate_name][expr.field]

    current = variable_types.AnyType()
    visited.add(expr)

    for neighbour, connection in graph.expression_connections[expr].items():
      if neighbour == expr or neighbour in visited:
        continue
      neighbour_type = self._infer_type(neighbour, visited, graph)
      # take 0th edge because algorithm does not support many edges for one variable yet
      constraint = self._get_neighbour_constraint(neighbour_type, connection[0])
      if type(current) is variable_types.AnyType:
        current = constraint
      else:
        if type(constraint) != variable_types.AnyType and constraint != current:
          raise TypeInferenceException()

    return current

  @staticmethod
  def _get_neighbour_constraint(neighbour_type: variable_types.Type, connection: edge.Edge) -> variable_types.Type:
    constraint = variable_types.AnyType()
    if type(connection) == edge.Equality:
      constraint = neighbour_type
    elif type(connection) == edge.EqualityOfElement:
      if type(neighbour_type) != variable_types.ListType:
        raise TypeInferenceException()
      constraint = cast(variable_types.ListType, neighbour_type).element
    # todo for other edges
    return constraint
