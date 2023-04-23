from collections import defaultdict
from typing import Set, cast

from type_inference.types import edge, expression
from type_inference.types import variable_types
from type_inference.types.types_graph import TypesGraph

literal_to_type = {expression.NumberLiteral(): variable_types.NumberType(),
                   expression.StringLiteral(): variable_types.StringType()}

inferred_rules = defaultdict(dict)
inferred_rules['Range']['col0'] = variable_types.NumberType()
inferred_rules['Range']['logica_value'] = variable_types.ListType(variable_types.NumberType())

graphs = dict()

def infer_type(expr: expression.Expression, visited: Set, graph: TypesGraph):
  if isinstance(expr, expression.Literal):
    return literal_to_type[expr]

  if isinstance(expr, expression.PredicateAddressing):
    if expr.predicate_name in inferred_rules:
      return inferred_rules[expr.predicate_name][expr.field]
    run(expr.predicate_name)
    return inferred_rules[expr.predicate_name][expr.field]

  current = None
  visited.add(expr)

  for neighbour, connection in graph.expression_connections[expr].items():
    if neighbour == expr or neighbour in visited:
      continue
    neighbour_type = infer_type(neighbour, visited, graph)
    constraint = None
    if type(connection[0]) == edge.Equality:
      constraint = neighbour_type
    elif type(connection[0]) == edge.EqualityOfElement:
      if type(neighbour_type) != variable_types.ListType:
        raise Exception
      constraint = (cast(variable_types.ListType, neighbour_type)).element
    if current is None:
      current = constraint
    else:
      if constraint != current:
        raise Exception

  return current

def wip(predicate_name: str):
  if predicate_name == 'Q':
    return [expression.Variable('x'), expression.Variable('y')]
  # return [expression.Variable('col0'), expression.Variable('logica_value')]
  return [expression.Variable('logica_value')]

def run(predicate_name: str):
  variables = wip(predicate_name)
  for variable in variables:
    var_type = infer_type(variable, set(), graphs[predicate_name])
    inferred_rules[predicate_name][variable.variable_name] = var_type



predicate = 'Q(x: 1, y:) :- y == P()'

graphQ = TypesGraph()
equalityEdgeX = edge.Equality(expression.Variable('x'), expression.NumberLiteral(), 0, 0)
equalityEdgeY = edge.Equality(expression.Variable('y'), expression.PredicateAddressing('P', 'logica_value'), 0, 0)
# equalityEdgeP = edge.Equality(expression.NumberLiteral(), expression.PredicateAddressing('P', 'col0'), 0, 0)
graphQ.connect(equalityEdgeX)
graphQ.connect(equalityEdgeY)
# graphQ.connect(equalityEdgeP)

predicateP = 'P() = a :- a in Range(10)'
# predicateP = 'P(a) = a :- a in Range(10)'
# 'P(a:, b: a) :- a in Range(10)'
graphP = TypesGraph()
# equalityEdgeA = edge.Equality(expression.Variable('col0'), expression.Variable('a'), 0, 0)
e3 = edge.Equality(expression.Variable('logica_value'), expression.Variable('a'), 0, 0)
eq1 = edge.EqualityOfElement(expression.PredicateAddressing('Range', 'logica_value'), expression.Variable('a'), 0, 0)
e2 = edge.Equality(expression.PredicateAddressing('Range', 'col0'), expression.NumberLiteral(), 0, 0)
# graphP.connect(equalityEdgeA)
graphP.connect(eq1)
graphP.connect(e2)
graphP.connect(e3)

graphs['Q'] = graphQ
graphs['P'] = graphP

run('Q')
for predicate_name, inferred_graph in inferred_rules.items():
  vars_to_print = []
  for var_name, var_type in inferred_graph.items():
    vars_to_print.append(f"{var_name}: {var_type}")
  print(f'{predicate_name}({", ".join(vars_to_print)})')
