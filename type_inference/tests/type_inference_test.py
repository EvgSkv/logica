from type_inference.types.types_graph import TypesGraph
from type_inference.types import edge, expression, variable_types
from type_inference.type_inference_service import TypeInferenceService
from type_inference import type_inference_service

import unittest
from unittest.mock import Mock, MagicMock

class TestTypeInference(unittest.TestCase):

  def test_when_connection_with_other_predicates(self):
    # 'Q(x) :- T(x), Num(x)'
    graph = TypesGraph()
    graph.connect(edge.Equality(expression.Variable('col0'), expression.Variable('x'), (0, 0)))
    graph.connect(edge.Equality(expression.Variable('x'), expression.PredicateAddressing('T', 'col0'), (0, 0)))
    graph.connect(edge.Equality(expression.Variable('x'), expression.PredicateAddressing('Num', 'col0'), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph
    type_inference_service.get_variables = Mock(return_value=[expression.Variable('col0'), expression.Variable('x')])

    inferred_rules = TypeInferenceService(graphs).infer_type('Q')

    self.assertIsInstance(inferred_rules['Q']['col0'], variable_types.NumberType)
    self.assertIsInstance(inferred_rules['Q']['x'], variable_types.NumberType)
    self.assertIsInstance(inferred_rules['T']['col0'], variable_types.AnyType)


  def test_when_plus_operator(self):
    # Q(x + y) :- T(x), T(y);
    graph = TypesGraph()
    x_var = expression.Variable('x')
    y_var = expression.Variable('y')
    graph.connect(edge.Equality(expression.Variable('col0'), expression.PredicateAddressing('+', 'logica_value'), (0, 0)))
    graph.connect(edge.Equality(x_var, expression.PredicateAddressing('+', 'col0'), (0, 0)))
    graph.connect(edge.Equality(y_var, expression.PredicateAddressing('+', 'col1'), (0, 0)))
    graph.connect(edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
    graph.connect(edge.Equality(y_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph
    type_inference_service.get_variables = Mock(return_value=[
      expression.Variable('col0'),
      expression.Variable('x'),
      expression.Variable('y')
    ])

    inferred_rules = TypeInferenceService(graphs).infer_type('Q')

    self.assertIsInstance(inferred_rules['Q']['col0'], variable_types.NumberType)
    self.assertIsInstance(inferred_rules['Q']['x'], variable_types.NumberType)
    self.assertIsInstance(inferred_rules['Q']['y'], variable_types.NumberType)
    # self.assertIsInstance(inferred_rules['T']['col0'], variable_types.NumberType)

  def test_when_str(self):
    # Q(x): - T(x), T(y), Str(x), x == y;
    graph = TypesGraph()
    x_var = expression.Variable('x')
    y_var = expression.Variable('y')
    graph.connect(edge.Equality(expression.Variable('col0'), expression.Variable('x'), (0, 0)))
    graph.connect(edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
    graph.connect(edge.Equality(y_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
    graph.connect(edge.Equality(x_var, expression.PredicateAddressing('Str', 'col0'), (0, 0)))
    graph.connect(edge.Equality(x_var, y_var, (0, 0)))
    graphs = dict()
    graphs['Q'] = graph
    type_inference_service.get_variables = Mock(return_value=[
      expression.Variable('col0'),
      expression.Variable('x'),
      expression.Variable('y')
    ])

    inferred_rules = TypeInferenceService(graphs).infer_type('Q')

    self.assertIsInstance(inferred_rules['Q']['col0'], variable_types.StringType)
    self.assertIsInstance(inferred_rules['Q']['x'], variable_types.StringType)
    self.assertIsInstance(inferred_rules['Q']['y'], variable_types.StringType)
    # self.assertIsInstance(inferred_rules['T']['col0'], variable_types.StringType)

  def test_when_concat_operator(self):
    # Q(x ++ y): - T(x), T(y);
    graph = TypesGraph()
    x_var = expression.Variable('x')
    y_var = expression.Variable('y')
    graph.connect(
      edge.Equality(expression.Variable('col0'), expression.PredicateAddressing('++', 'logica_value'), (0, 0)))
    graph.connect(edge.Equality(x_var, expression.PredicateAddressing('++', 'col0'), (0, 0)))
    graph.connect(edge.Equality(y_var, expression.PredicateAddressing('++', 'col1'), (0, 0)))
    graph.connect(edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
    graph.connect(edge.Equality(y_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph
    type_inference_service.get_variables = Mock(return_value=[
      expression.Variable('col0'),
      expression.Variable('x'),
      expression.Variable('y')
    ])

    inferred_rules = TypeInferenceService(graphs).infer_type('Q')

    self.assertIsInstance(inferred_rules['Q']['col0'], variable_types.StringType)
    self.assertIsInstance(inferred_rules['Q']['x'], variable_types.StringType)
    self.assertIsInstance(inferred_rules['Q']['y'], variable_types.StringType)
    # self.assertIsInstance(inferred_rules['T']['col0'], variable_types.StringType)

  def test_when_in_operator(self):
    # Q(y): - T(x), y in x, Num(y);
    graph = TypesGraph()
    x_var = expression.Variable('x')
    y_var = expression.Variable('y')
    graph.connect(edge.Equality(expression.Variable('col0'), y_var, (0, 0)))
    graph.connect(edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
    graph.connect(edge.Equality(y_var, expression.PredicateAddressing('Num', 'col0'), (0, 0)))
    graph.connect(edge.EqualityOfElement(x_var, y_var, (0, 0)))
    graphs = dict()
    graphs['Q'] = graph
    type_inference_service.get_variables = Mock(return_value=[
      expression.Variable('col0'),
      expression.Variable('x'),
      expression.Variable('y')
    ])

    inferred_rules = TypeInferenceService(graphs).infer_type('Q')

    self.assertIsInstance(inferred_rules['Q']['col0'], variable_types.NumberType)
    self.assertIsInstance(inferred_rules['Q']['x'], variable_types.ListType)
    self.assertIsInstance(inferred_rules['Q']['y'], variable_types.NumberType)
    # self.assertIsInstance(inferred_rules['T']['col0'], variable_types.ListType)

  def test_when_record(self):
    # Q(p: Str(y), q: z + w, s: x):- T(x), y == x.a, z == x.b, w == x.c.d;
    pass

  def test_when_named_columns(self):
    # Q(a:, b:):- T(x), T(y), a == x + y, b == x + y;
    graph = TypesGraph()
    x_var = expression.Variable('x')
    y_var = expression.Variable('y')
    a_var = expression.Variable('a')
    b_var = expression.Variable('b')
    graph.connect(edge.Equality(a_var, a_var, (0, 0)))
    graph.connect(edge.Equality(b_var, b_var, (0, 0)))
    graph.connect(edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
    graph.connect(edge.Equality(y_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
    graph.connect(edge.Equality(a_var, expression.PredicateAddressing('+', 'logica_value'), (0, 0)))
    graph.connect(edge.Equality(b_var, expression.PredicateAddressing('+', 'logica_value'), (0, 0)))
    graph.connect(edge.Equality(x_var, expression.PredicateAddressing('+', 'col0'), (0, 0)))
    graph.connect(edge.Equality(y_var, expression.PredicateAddressing('+', 'col1'), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    def side_effect_function(rule: str):
      if rule == 'Q':
        return [a_var, b_var, x_var, y_var]
      else:
        return [expression.Variable('col0')]

    m = MagicMock(side_effect=side_effect_function)
    type_inference_service.get_variables = Mock(side_effect=side_effect_function)

    inferred_rules = TypeInferenceService(graphs).infer_type('Q')

    self.assertIsInstance(inferred_rules['Q']['a'], variable_types.NumberType)
    self.assertIsInstance(inferred_rules['Q']['b'], variable_types.NumberType)
    self.assertIsInstance(inferred_rules['Q']['x'], variable_types.NumberType)
    self.assertIsInstance(inferred_rules['Q']['y'], variable_types.NumberType)
    # self.assertIsInstance(inferred_rules['T']['col0'], variable_types.NumberType)
    # self.assertIsInstance(inferred_rules['T']['col1'], variable_types.NumberType)

    # for predicate_name, inferred_graph in inferred_rules.items():
    #   vars_to_print = []
    #   for var_name, var_type in inferred_graph.items():
    #     vars_to_print.append(f"{var_name}: {var_type}")
    #   print(f'{predicate_name}({", ".join(vars_to_print)})')