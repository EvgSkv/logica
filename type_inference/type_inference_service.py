from collections import defaultdict
from typing import Set

from type_inference.type_inference_exception import TypeInferenceException
from type_inference.types import edge, expression
from type_inference.types.types_graph import TypesGraph, get_variables
from type_inference.types.variable_types import *

number_type = NumberType()
string_type = StringType()

literal_to_type = {expression.NumberLiteral(): number_type,
                   expression.StringLiteral(): string_type}

inferred_rules = defaultdict(dict)

inferred_rules['Range']['col0'] = number_type
inferred_rules['Range']['logica_value'] = ListType(number_type)

inferred_rules['Num']['col0'] = number_type
inferred_rules['Num']['logica_value'] = number_type

inferred_rules['Str']['col0'] = string_type
inferred_rules['Str']['logica_value'] = string_type

inferred_rules['+']['col0'] = number_type
inferred_rules['+']['col1'] = number_type
inferred_rules['+']['logica_value'] = number_type

inferred_rules['++']['col0'] = string_type
inferred_rules['++']['col1'] = string_type
inferred_rules['++']['logica_value'] = string_type


class TypeInference:
  def __init__(self, graphs: dict):
    self.graphs = graphs

  def infer_type(self, rule: str):
    variables = get_variables(rule)
    for variable in variables:
      if rule in self.graphs:
        var_type = self._infer_type(variable, set(), self.graphs[rule])
      else:
        var_type = AnyType()
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

    current = AnyType()
    visited.add(expr)

    for neighbour, connection in graph.expression_connections[expr].items():
      if neighbour == expr or neighbour in visited:
        continue
      neighbour_type = self._infer_type(neighbour, visited, graph)
      # take 0th edge because algorithm does not support many edges for one variable yet
      constraint = self._get_constraint(neighbour_type, connection[0], expr, neighbour)
      if type(current) is AnyType:
        current = constraint
      else:
        if type(constraint) != AnyType and constraint != current:
          raise TypeInferenceException()
        elif isinstance(constraint, RecordType) and isinstance(current, RecordType):
          set1 = set(current.fields)
          set2 = set(constraint.fields)
          union = set1.union(set2)
          if not current.is_opened:
            if len(set1) != len(union):
              raise Exception
          else:
            current.fields = list(union)
    return current

  @staticmethod
  def _get_constraint(neighbour_type: Type, connection: edge.Edge, expr: expression.Expression, neighbour: expression.Expression) -> Type:
    constraint = AnyType()
    if isinstance(connection, edge.Equality):
      constraint = neighbour_type
    elif isinstance(connection, edge.EqualityOfElement):
      if not isinstance(neighbour_type, ListType) and not isinstance(neighbour_type, AnyType):
        # TODO check for bug here
        constraint = ListType(neighbour_type)
      else:
        constraint = cast(ListType, neighbour_type).element if type(neighbour_type) == ListType else AnyType()
    elif isinstance(connection, edge.FieldBelonging):
      if expr == connection.vertices[0]:
        # x.b (x)
        constraint = RecordType([Field(connection.field.subscript_field, neighbour_type)], True)
      else:
        neighbour_type = cast(neighbour_type, RecordType)
        for field in neighbour_type.fields:
          if field.name == connection.field.subscript_field:
            constraint = field.type
            break
        else:
          if not neighbour_type.is_opened:
            raise Exception
          constraint = AnyType

    return constraint
