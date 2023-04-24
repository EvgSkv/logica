from type_inference.types.types_graph import TypesGraph
from type_inference.types import edge, expression
from type_inference.type_inference_service import TypeInferenceService

predicate = 'Q(x) :- T(x), Num(x)'

graphQ = TypesGraph()
edge1 = edge.Equality(expression.Variable('col0'), expression.Variable('x'), 0, 0)
edge2 = edge.Equality(expression.Variable('x'), expression.PredicateAddressing('T', 'col0'), 0, 0)
edge3 = edge.Equality(expression.Variable('x'), expression.PredicateAddressing('Num', 'col0'), 0, 0)
graphQ.connect(edge1)
graphQ.connect(edge2)
graphQ.connect(edge3)

graphs = dict()
graphs['Q'] = graphQ

inferred_rules = TypeInferenceService(graphs).infer_type('Q') # to make it work change types_graph.get_variables
for predicate_name, inferred_graph in inferred_rules.items():
  vars_to_print = []
  for var_name, var_type in inferred_graph.items():
    vars_to_print.append(f"{var_name}: {var_type}")
  print(f'{predicate_name}({", ".join(vars_to_print)})')