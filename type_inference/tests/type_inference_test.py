import unittest

from type_inference.type_inference_service import TypeInference
from type_inference.types import edge, expression
from type_inference.types.types_graph import TypesGraph
from type_inference.types.variable_types import NumberType, StringType, ListType, RecordType

number = NumberType()
string = StringType()

class TestTypeInferenceSucceeded(unittest.TestCase):

  def test_when_num(self):
    # 'Q(x) :- x == 1'
    graph = TypesGraph()
    q_col0 = expression.Variable('col0')
    x_var = expression.Variable('x')
    graph.connect(edge.Equality(q_col0, x_var, (0, 0)))
    graph.connect(edge.Equality(x_var, expression.NumberLiteral(), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    self.assertEquals(q_col0.type, number)
    self.assertEquals(x_var.type, number)

  def test_when_linked_with_unknown_predicate(self):
    # 'Q(x) :- T(x), Num(x)'
    graph = TypesGraph()
    q_col0 = expression.Variable('col0')
    t_col0 = expression.PredicateAddressing('T', 'col0')
    x_var = expression.Variable('x')
    graph.connect(edge.Equality(q_col0, x_var, (0, 0)))
    graph.connect(edge.Equality(x_var, t_col0, (0, 0)))
    graph.connect(edge.Equality(x_var, expression.PredicateAddressing('Num', 'col0'), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    self.assertEquals(q_col0.type, number)
    self.assertEquals(t_col0.type, number)

  def test_when_inclusion(self):
    # Q(x) :- x in Range(10)
    graph = TypesGraph()
    q_col0 = expression.Variable('col0')
    x_var = expression.Variable('x')
    graph.connect(edge.Equality(q_col0, x_var, (0, 0)))
    graph.connect(edge.EqualityOfElement(expression.PredicateAddressing('Range', 'logica_value'), x_var, (0, 0)))
    graph.connect(edge.Equality(expression.PredicateAddressing('Range', 'col0'), expression.NumberLiteral(), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    self.assertEqual(q_col0.type, number)
    self.assertEqual(x_var.type, number)

  def test_when_list(self):
    # Q(Range(10));
    graph = TypesGraph()
    q_col0 = expression.Variable('col0')
    graph.connect(edge.Equality(expression.PredicateAddressing('Range', 'logica_value'), q_col0, (0, 0)))
    graph.connect(edge.Equality(expression.PredicateAddressing('Range', 'col0'), expression.NumberLiteral(), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    self.assertEquals(q_col0.type, ListType(number))

  def test_when_opened_record(self):
    # Q(x) :- x.a == 1, x.b == "string"
    graph = TypesGraph()
    q_col0 = expression.Variable('col0')
    x_var = expression.Variable('x')
    a = expression.SubscriptAddressing(x_var, 'a')
    b = expression.SubscriptAddressing(x_var, 'b')
    graph.connect(edge.Equality(q_col0, x_var, (0, 0)))
    graph.connect(edge.FieldBelonging(x_var, a, (0, 0)))
    graph.connect(edge.FieldBelonging(x_var, b, (0, 0)))
    graph.connect(edge.Equality(a, expression.NumberLiteral(), (0, 0)))
    graph.connect(edge.Equality(b, expression.StringLiteral(), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    self.assertEquals(q_col0.type, RecordType({'a': number, 'b': string}, True))

  def test_when_opened_record_with_opened_record(self):
    # Q(x) :- x.a == 1, x.b.c == "string"
    graph = TypesGraph()
    q_col0 = expression.Variable('col0')
    x_var = expression.Variable('x')
    a = expression.SubscriptAddressing(x_var, 'a')
    b = expression.SubscriptAddressing(x_var, 'b')
    c = expression.SubscriptAddressing(b, 'c')
    graph.connect(edge.Equality(q_col0, x_var, (0, 0)))
    graph.connect(edge.FieldBelonging(x_var, a, (0, 0)))
    graph.connect(edge.FieldBelonging(x_var, b, (0, 0)))
    graph.connect(edge.FieldBelonging(b, c, (0, 0)))
    graph.connect(edge.Equality(a, expression.NumberLiteral(), (0, 0)))
    graph.connect(edge.Equality(c, expression.StringLiteral(), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    self.assertEquals(q_col0.type, RecordType({'a': number, 'b': RecordType({'c': string}, True)}, True))

  # todo fix it
  # def test_when_linked_with_known_predicate(self):
  #   # Q(x) :- T(x), Num(x)
  #   # T(x) :- x == 10
  #   graph = TypesGraph()
  #   x_var = expression.Variable('x')
  #   graph.connect(edge.Equality(expression.Variable('col0'), x_var, (0, 0)))
  #   graph.connect(edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
  #   graph.connect(edge.Equality(x_var, expression.PredicateAddressing('Num', 'col0'), (0, 0)))
  #   graphs = dict()
  #   graphs['Q'] = graph
  #
  #   graphT = TypesGraph()
  #   graphT.connect(edge.Equality(expression.Variable('col0'), expression.Variable('x'), (0, 0)))
  #   graphT.connect(edge.Equality(expression.Variable('x'), expression.NumberLiteral(), (0, 0)))
  #
  #   graphs['T'] = graphT
  #
  #   type_inference_service.get_variables = Mock(return_value=[expression.Variable('col0'), expression.Variable('x')])
  #
  #   inferred_rules = TypeInference(graphs).infer_type('Q')
  #
  #   self.assertIsInstance(inferred_rules['Q']['col0'], variable_types.NumberType)
  #   self.assertIsInstance(inferred_rules['Q']['x'], variable_types.NumberType)
  #   self.assertIsInstance(inferred_rules['T']['col0'], variable_types.NumberType)
  #   self.assertIsInstance(inferred_rules['T']['x'], variable_types.NumberType)
  #
  # def test_when_plus_operator_old(self):
  #   # Q(x + y) :- T(x), T(y);
  #   # T(x) :- x == 1
  #   graph = TypesGraph()
  #   x_var = expression.Variable('x')
  #   y_var = expression.Variable('y')
  #   graph.connect(edge.Equality(expression.Variable('col0'), expression.PredicateAddressing('+', 'logica_value'), (0, 0)))
  #   graph.connect(edge.Equality(x_var, expression.PredicateAddressing('+', 'col0'), (0, 0)))
  #   graph.connect(edge.Equality(y_var, expression.PredicateAddressing('+', 'col1'), (0, 0)))
  #   graph.connect(edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
  #   graph.connect(edge.Equality(y_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
  #   graphs = dict()
  #   graphs['Q'] = graph
  #
  #   def side_effect_function(rule: str):
  #     if rule == 'Q':
  #       return [ expression.Variable('col0'),
  #     expression.Variable('x'),
  #     expression.Variable('y')]
  #     else:
  #       return [expression.Variable('col0'), expression.Variable('x')]
  #
  #   type_inference_service.get_variables = Mock(side_effect=side_effect_function)
  #
  #   type_inference_service.get_variables = Mock(return_value=[
  #     expression.Variable('col0'),
  #     expression.Variable('x'),
  #     expression.Variable('y')
  #   ])
  #
  #   graphT = TypesGraph()
  #   graphT.connect(edge.Equality(expression.Variable('col0'), expression.Variable('x'), (0, 0)))
  #   graphT.connect(edge.Equality(expression.Variable('x'), expression.NumberLiteral(), (0, 0)))
  #
  #   graphs['T'] = graphT
  #
  #   inferred_rules = TypeInference(graphs).infer_type('Q')
  #
  #   self.assertIsInstance(inferred_rules['Q']['col0'], variable_types.NumberType)
  #   self.assertIsInstance(inferred_rules['Q']['x'], variable_types.NumberType)
  #   self.assertIsInstance(inferred_rules['Q']['y'], variable_types.NumberType)
  #   self.assertIsInstance(inferred_rules['T']['col0'], variable_types.NumberType)
  #   self.assertIsInstance(inferred_rules['T']['x'], variable_types.NumberType)
  #
  # def test_when_str(self):
  #   # Q(x): - T(x), T(y), Str(x), x == y;
  #   graph = TypesGraph()
  #   x_var = expression.Variable('x')
  #   y_var = expression.Variable('y')
  #   graph.connect(edge.Equality(expression.Variable('col0'), expression.Variable('x'), (0, 0)))
  #   graph.connect(edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
  #   graph.connect(edge.Equality(y_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
  #   graph.connect(edge.Equality(x_var, expression.PredicateAddressing('Str', 'col0'), (0, 0)))
  #   graph.connect(edge.Equality(x_var, y_var, (0, 0)))
  #   graphs = dict()
  #   graphs['Q'] = graph
  #   type_inference_service.get_variables = Mock(return_value=[
  #     expression.Variable('col0'),
  #     expression.Variable('x'),
  #     expression.Variable('y')
  #   ])
  #
  #   inferred_rules = TypeInference(graphs).infer_type('Q')
  #
  #   self.assertIsInstance(inferred_rules['Q']['col0'], variable_types.StringType)
  #   self.assertIsInstance(inferred_rules['Q']['x'], variable_types.StringType)
  #   self.assertIsInstance(inferred_rules['Q']['y'], variable_types.StringType)
  #   # self.assertIsInstance(inferred_rules['T']['col0'], variable_types.StringType)
  #
  # def test_when_concat_operator(self):
  #   # Q(x ++ y): - T(x), T(y);
  #   graph = TypesGraph()
  #   x_var = expression.Variable('x')
  #   y_var = expression.Variable('y')
  #   graph.connect(
  #     edge.Equality(expression.Variable('col0'), expression.PredicateAddressing('++', 'logica_value'), (0, 0)))
  #   graph.connect(edge.Equality(x_var, expression.PredicateAddressing('++', 'col0'), (0, 0)))
  #   graph.connect(edge.Equality(y_var, expression.PredicateAddressing('++', 'col1'), (0, 0)))
  #   graph.connect(edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
  #   graph.connect(edge.Equality(y_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
  #   graphs = dict()
  #   graphs['Q'] = graph
  #   type_inference_service.get_variables = Mock(return_value=[
  #     expression.Variable('col0'),
  #     expression.Variable('x'),
  #     expression.Variable('y')
  #   ])
  #
  #   inferred_rules = TypeInference(graphs).infer_type('Q')
  #
  #   self.assertIsInstance(inferred_rules['Q']['col0'], variable_types.StringType)
  #   self.assertIsInstance(inferred_rules['Q']['x'], variable_types.StringType)
  #   self.assertIsInstance(inferred_rules['Q']['y'], variable_types.StringType)
  #   # self.assertIsInstance(inferred_rules['T']['col0'], variable_types.StringType)
  #
  # def test_when_in_operator(self):
  #   # Q(y): - T(x), y in x, Num(y);
  #   graph = TypesGraph()
  #   x_var = expression.Variable('x')
  #   y_var = expression.Variable('y')
  #   graph.connect(edge.Equality(expression.Variable('col0'), y_var, (0, 0)))
  #   graph.connect(edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
  #   graph.connect(edge.Equality(y_var, expression.PredicateAddressing('Num', 'col0'), (0, 0)))
  #   graph.connect(edge.EqualityOfElement(x_var, y_var, (0, 0)))
  #   graphs = dict()
  #   graphs['Q'] = graph
  #   type_inference_service.get_variables = Mock(return_value=[
  #     expression.Variable('col0'),
  #     expression.Variable('x'),
  #     expression.Variable('y')
  #   ])
  #
  #   inferred_rules = TypeInference(graphs).infer_type('Q')
  #
  #   self.assertIsInstance(inferred_rules['Q']['col0'], variable_types.NumberType)
  #   self.assertIsInstance(inferred_rules['Q']['x'], variable_types.ListType)
  #   self.assertIsInstance(inferred_rules['Q']['y'], variable_types.NumberType)
  #   # self.assertIsInstance(inferred_rules['T']['col0'], variable_types.ListType)
  #
  # def test_when_simple_nested_record(self):
  #   # Q(x) :- x.a == 1, x.b == {c: "string", d: "another string"}, y == x
  #   graph = TypesGraph()
  #   graphs = dict()
  #   graphs['Q'] = graph
  #   x_var = expression.Variable('x')
  #   a = expression.SubscriptAddressing(x_var, 'a')
  #   b = expression.SubscriptAddressing(x_var, 'b')
  #   graph.connect(edge.Equality(expression.Variable('col0'), x_var, (0, 0)))
  #   graph.connect(edge.FieldBelonging(x_var, a, (0, 0)))
  #   graph.connect(edge.FieldBelonging(x_var, b, (0, 0)))
  #   graph.connect(edge.Equality(b, expression.RecordLiteral({'c': expression.StringLiteral(), 'd': expression.StringLiteral()}), (0, 0)))
  #   graph.connect(edge.Equality(a, expression.NumberLiteral(), (0, 0)))
  #   graph.connect(edge.Equality(expression.Variable('y'), x_var, (0, 0)))
  #
  #   TypeInference(graphs).Infer()
  #
  #   print()
  #
  # def test_when_simplest_record(self):
  #   # Q(x) :- x.a == 1, x.b == Range(10)
  #   graph = TypesGraph()
  #   graphs = dict()
  #   graphs['Q'] = graph
  #   x_var = expression.Variable('x')
  #   a = expression.SubscriptAddressing(x_var, 'a')
  #   b = expression.SubscriptAddressing(x_var, 'b')
  #   graph.connect(edge.Equality(expression.Variable('col0'), x_var, (0, 0)))
  #   graph.connect(edge.FieldBelonging(x_var, a, (0, 0)))
  #   graph.connect(edge.FieldBelonging(x_var, b, (0, 0)))
  #   graph.connect(edge.Equality(a, expression.NumberLiteral(), (0, 0)))
  #   graph.connect(edge.Equality(b, expression.PredicateAddressing('Range', 'logica_value'), (0, 0)))
  #
  #   TypeInference(graphs).Infer()
  #
  #   print()

  # def test_when_record(self):
  #   # Q(p: Str(y), q: z + w, s: x):- T(x), y == x.a, z == x.b, w == x.c;
  #   graph = TypesGraph()
  #   p_var = expression.Variable('p')
  #   q_var = expression.Variable('q')
  #   s_var = expression.Variable('s')
  #   y_var = expression.Variable('y')
  #   z_var = expression.Variable('z')
  #   w_var = expression.Variable('w')
  #   x_var = expression.Variable('x')
  #
  #   expected = [edge.Equality(p_var, expression.PredicateAddressing("Str", "logica_value"), (0, 0)),
  #               edge.Equality(y_var, expression.PredicateAddressing("Str", "col0"), (0, 0)),
  #               edge.Equality(q_var, expression.PredicateAddressing("+", "logica_value"), (0, 0)),
  #               edge.Equality(z_var, expression.PredicateAddressing("+", "left"), (0, 0)),
  #               edge.Equality(w_var, expression.PredicateAddressing("+", "right"), (0, 0)),
  #               edge.Equality(s_var, x_var, (0, 0)),
  #               edge.Equality(x_var, expression.PredicateAddressing("T", "col0"), (0, 0)),
  #               edge.Equality(expression.SubscriptAddressing(x_var, 'a'), y_var, (0, 0)),
  #               edge.Equality(expression.SubscriptAddressing(x_var, 'b'), z_var, (0, 0)),
  #               edge.Equality(expression.SubscriptAddressing(x_var, 'c'), w_var, (0, 0)),
  #               edge.FieldBelonging(x_var, expression.SubscriptAddressing(x_var, 'a'), (0, 0)),
  #               edge.FieldBelonging(x_var, expression.SubscriptAddressing(x_var, 'b'), (0, 0)),
  #               edge.FieldBelonging(x_var, expression.SubscriptAddressing(x_var, 'c'), (0, 0))]
  #
  #   for e in expected:
  #     graph.connect(e)
  #
  #   graphs = dict()
  #   graphs['Q'] = graph
  #
  #   def side_effect_function(rule: str):
  #     if rule == 'Q':
  #       return [p_var, q_var, s_var, y_var, z_var, w_var, x_var]
  #     else:
  #       return [expression.Variable('col0')]
  #
  #   type_inference_service.get_variables = Mock(side_effect=side_effect_function)
  #
  #   inferred_rules = TypeInference(graphs).try_inference('Q')
  #
  #   for predicate_name, inferred_graph in inferred_rules.items():
  #     vars_to_print = []
  #     for var_name, var_type in inferred_graph.items():
  #       vars_to_print.append(f"{var_name}: {var_type}")
  #     print(f'{predicate_name}({", ".join(vars_to_print)})')
  #
  # def test_when_record1(self):
  #   # Q(p: Str(y), q: z + w, s: x):- T(x), y == x.a, z == x.b, w == x.c.d;
  #   graph = TypesGraph()
  #   p_var = expression.Variable('p')
  #   q_var = expression.Variable('q')
  #   s_var = expression.Variable('s')
  #   y_var = expression.Variable('y')
  #   z_var = expression.Variable('z')
  #   w_var = expression.Variable('w')
  #   x_var = expression.Variable('x')
  #
  #   expected = [edge.Equality(p_var, expression.PredicateAddressing("Str", "logica_value"), (0, 0)),
  #               # edge.PredicateArgument(expression.PredicateAddressing('Str', 'logica_value'),
  #               #                        expression.PredicateAddressing('Str', 'col0'), (0, 0)),
  #               edge.Equality(y_var, expression.PredicateAddressing("Str", "col0"), (0, 0)),
  #               edge.Equality(q_var, expression.PredicateAddressing("+", "logica_value"), (0, 0)),
  #               # edge.PredicateArgument(expression.PredicateAddressing('+', 'logica_value'),
  #               #                        expression.PredicateAddressing('+', 'left'), (0, 0)),
  #               # edge.PredicateArgument(expression.PredicateAddressing('+', 'logica_value'),
  #               #                        expression.PredicateAddressing('+', 'right'), (0, 0)),
  #               edge.Equality(z_var, expression.PredicateAddressing("+", "left"), (0, 0)),
  #               edge.Equality(w_var, expression.PredicateAddressing("+", "right"), (0, 0)),
  #               edge.Equality(s_var, x_var, (0, 0)),
  #               edge.Equality(x_var, expression.PredicateAddressing("T", "col0"), (0, 0)),
  #               edge.Equality(expression.SubscriptAddressing(x_var, 'a'), y_var, (0, 0)),
  #               edge.Equality(expression.SubscriptAddressing(x_var, 'b'), z_var, (0, 0)),
  #               edge.Equality(expression.SubscriptAddressing(expression.SubscriptAddressing(x_var, 'c'), 'd'), w_var,
  #                             (0, 0)),
  #               edge.FieldBelonging(x_var, expression.SubscriptAddressing(x_var, 'a'), (0, 0)),
  #               edge.FieldBelonging(x_var, expression.SubscriptAddressing(x_var, 'b'), (0, 0)),
  #               edge.FieldBelonging(x_var, expression.SubscriptAddressing(x_var, 'c'), (0, 0)),
  #               edge.FieldBelonging(expression.SubscriptAddressing(x_var, 'c'),
  #                                   expression.SubscriptAddressing(expression.SubscriptAddressing(x_var, 'c'), 'd'),
  #                                   (0, 0))]
  #
  #   for e in expected:
  #     graph.connect(e)
  #
  #   graphs = dict()
  #   graphs['Q'] = graph
  #
  #   def side_effect_function(rule: str):
  #     if rule == 'Q':
  #       return [p_var, q_var, s_var, y_var, z_var, w_var, x_var]
  #     else:
  #       return [expression.Variable('col0')]
  #
  #   type_inference_service.get_variables = Mock(side_effect=side_effect_function)
  #
  #   inferred_rules = TypeInference(graphs).infer_type('Q')
  #
  #   for predicate_name, inferred_graph in inferred_rules.items():
  #     vars_to_print = []
  #     for var_name, var_type in inferred_graph.items():
  #       vars_to_print.append(f"{var_name}: {var_type}")
  #     print(f'{predicate_name}({", ".join(vars_to_print)})')
  #
  # def test_when_named_columns(self):
  #   # Q(a:, b:):- T(x), T(y), a == x + y, b == x + y;
  #   graph = TypesGraph()
  #   x_var = expression.Variable('x')
  #   y_var = expression.Variable('y')
  #   a_var = expression.Variable('a')
  #   b_var = expression.Variable('b')
  #   graph.connect(edge.Equality(a_var, a_var, (0, 0)))
  #   graph.connect(edge.Equality(b_var, b_var, (0, 0)))
  #   graph.connect(edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
  #   graph.connect(edge.Equality(y_var, expression.PredicateAddressing('T', 'col0'), (0, 0)))
  #   graph.connect(edge.Equality(a_var, expression.PredicateAddressing('+', 'logica_value'), (0, 0)))
  #   graph.connect(edge.Equality(b_var, expression.PredicateAddressing('+', 'logica_value'), (0, 0)))
  #   graph.connect(edge.Equality(x_var, expression.PredicateAddressing('+', 'col0'), (0, 0)))
  #   graph.connect(edge.Equality(y_var, expression.PredicateAddressing('+', 'col1'), (0, 0)))
  #   graphs = dict()
  #   graphs['Q'] = graph
  #
  #   def side_effect_function(rule: str):
  #     if rule == 'Q':
  #       return [a_var, b_var, x_var, y_var]
  #     else:
  #       return [expression.Variable('col0')]
  #
  #   m = MagicMock(side_effect=side_effect_function)
  #   type_inference_service.get_variables = Mock(side_effect=side_effect_function)
  #
  #   inferred_rules = TypeInference(graphs).infer_type('Q')
  #
  #   self.assertIsInstance(inferred_rules['Q']['a'], variable_types.NumberType)
  #   self.assertIsInstance(inferred_rules['Q']['b'], variable_types.NumberType)
  #   self.assertIsInstance(inferred_rules['Q']['x'], variable_types.NumberType)
  #   self.assertIsInstance(inferred_rules['Q']['y'], variable_types.NumberType)
    # self.assertIsInstance(inferred_rules['T']['col0'], variable_types.NumberType)
    # self.assertIsInstance(inferred_rules['T']['col1'], variable_types.NumberType)

    # for predicate_name, inferred_graph in inferred_rules.items():
    #   vars_to_print = []
    #   for var_name, var_type in inferred_graph.items():
    #     vars_to_print.append(f"{var_name}: {var_type}")
    #   print(f'{predicate_name}({", ".join(vars_to_print)})')