from queue import Queue
from type_inference.types.types_graph import TypesGraph
from type_inference.types import edge, expression
from typing import Set
from collections import defaultdict
from type_inference.types import variable_types

literal_to_type = dict()
literal_to_type[expression.NumberLiteral()] = variable_types.NumberType()
literal_to_type[expression.StringLiteral()] = variable_types.StringType()

d = dict()

inferred_graphs = defaultdict(dict)
inferred_graphs['Range']['col0'] = variable_types.NumberType()
inferred_graphs['Range']['logica_value'] = variable_types.ListType(variable_types.NumberType())

def infer_type(variable: expression.Expression, visited: Set, graph: TypesGraph):
  if isinstance(variable, expression.Literal):
    return literal_to_type[variable]

  if isinstance(variable, expression.PredicateAddressing):
    if variable.predicate_name in inferred_graphs:
      return inferred_graphs[variable.predicate_name][variable.field]
    run(variable.predicate_name)
    return inferred_graphs[variable.predicate_name][variable.field]

  current = None
  visited.add(variable)

  for neighbour in graph.expression_connections[variable]:
    if neighbour == variable or neighbour in visited:
      continue
    k = infer_type(neighbour, visited, graph)
    if current is None:
      current = k
    else:
      if k != current:
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
    var_type = infer_type(variable, set(), d[predicate_name])
    inferred_graphs[predicate_name][variable.variable_name] = var_type


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

d['Q'] = graphQ
d['P'] = graphP

run('Q')
for (predicate_name, inferred_graph) in inferred_graphs.items():
  print(f'{predicate_name}: {inferred_graph}')
