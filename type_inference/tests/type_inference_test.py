import unittest

from type_inference.type_inference_service import TypeInference
from type_inference.types.edge import Equality, EqualityOfElement, FieldBelonging
from type_inference.types.expression import Variable, PredicateAddressing, NumberLiteral, SubscriptAddressing, \
  StringLiteral
from type_inference.types.types_graph import TypesGraph
from type_inference.types.variable_types import NumberType, StringType, ListType, RecordType

number = NumberType()
string = StringType()


class TestTypeInference(unittest.TestCase):
  def test_when_num(self):
    # 'Q(x) :- x == 1'
    graph = TypesGraph()
    q_col0 = Variable('col0')
    x_var = Variable('x')
    graph.Connect(Equality(q_col0, x_var, (0, 0)))
    graph.Connect(Equality(x_var, NumberLiteral(), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    self.assertEqual(q_col0.type, number)
    self.assertEqual(x_var.type, number)

  def test_when_inclusion(self):
    # Q(x) :- x in Range(10)
    graph = TypesGraph()
    q_col0 = Variable('col0')
    x_var = Variable('x')
    graph.Connect(Equality(q_col0, x_var, (0, 0)))
    graph.Connect(EqualityOfElement(PredicateAddressing('Range', 'logica_value'), x_var, (0, 0)))
    graph.Connect(Equality(PredicateAddressing('Range', 'col0'), NumberLiteral(), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    self.assertEqual(q_col0.type, number)
    self.assertEqual(x_var.type, number)

  def test_when_list(self):
    # Q(Range(10));
    graph = TypesGraph()
    q_col0 = Variable('col0')
    graph.Connect(Equality(PredicateAddressing('Range', 'logica_value'), q_col0, (0, 0)))
    graph.Connect(Equality(PredicateAddressing('Range', 'col0'), NumberLiteral(), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    self.assertEqual(q_col0.type, ListType(number))

  def test_when_opened_record(self):
    # Q(x) :- x.a == 1, x.b == "string"
    graph = TypesGraph()
    q_col0 = Variable('col0')
    x_var = Variable('x')
    a = SubscriptAddressing(x_var, 'a')
    b = SubscriptAddressing(x_var, 'b')
    graph.Connect(Equality(q_col0, x_var, (0, 0)))
    graph.Connect(FieldBelonging(x_var, a, (0, 0)))
    graph.Connect(FieldBelonging(x_var, b, (0, 0)))
    graph.Connect(Equality(a, NumberLiteral(), (0, 0)))
    graph.Connect(Equality(b, StringLiteral(), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    self.assertEqual(q_col0.type, RecordType({'a': number, 'b': string}, True))

  def test_when_opened_record_with_opened_record(self):
    # Q(x) :- x.a == 1, x.b.c == "string"
    graph = TypesGraph()
    q_col0 = Variable('col0')
    x_var = Variable('x')
    a = SubscriptAddressing(x_var, 'a')
    b = SubscriptAddressing(x_var, 'b')
    c = SubscriptAddressing(b, 'c')
    graph.Connect(Equality(q_col0, x_var, (0, 0)))
    graph.Connect(FieldBelonging(x_var, a, (0, 0)))
    graph.Connect(FieldBelonging(x_var, b, (0, 0)))
    graph.Connect(FieldBelonging(b, c, (0, 0)))
    graph.Connect(Equality(a, NumberLiteral(), (0, 0)))
    graph.Connect(Equality(c, StringLiteral(), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    self.assertEqual(q_col0.type, RecordType({'a': number, 'b': RecordType({'c': string}, True)}, True))

  def test_when_linked_with_known_predicates(self):
    # Q(x, y) :- T(x), Num(x), y == F(x);
    # T(x) :- x == 10;
    # F(x) :- x;
    graph_q = TypesGraph()
    x_var_q = Variable('x')
    y_var_q = Variable('y')
    graph_q.Connect(Equality(PredicateAddressing('Q', 'col0'), x_var_q, (0, 0)))
    graph_q.Connect(Equality(PredicateAddressing('Q', 'col1'), y_var_q, (0, 0)))
    graph_q.Connect(Equality(x_var_q, PredicateAddressing('T', 'col0'), (0, 0)))
    graph_q.Connect(Equality(x_var_q, PredicateAddressing('F', 'col0'), (0, 0)))
    graph_q.Connect(Equality(x_var_q, y_var_q, (0, 0)))
    graph_q.Connect(Equality(x_var_q, PredicateAddressing('Num', 'col0'), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph_q

    graph_t = TypesGraph()
    x_var_t = Variable('x')
    graph_t.Connect(Equality(PredicateAddressing('T', 'col0'), x_var_t, (0, 0)))
    graph_t.Connect(Equality(x_var_t, NumberLiteral(), (0, 0)))
    graphs['T'] = graph_t

    graph_f = TypesGraph()
    x_var_f = Variable('x')
    graph_f.Connect(Equality(PredicateAddressing('F', 'col0'), x_var_f, (0, 0)))
    graphs['F'] = graph_f

    TypeInference(graphs).Infer()

    self.assertEqual(x_var_t.type, number)
    self.assertEqual(y_var_q.type, number)

  def test_when_field_is_function_result(self):
    # Q(x) :- x.a == T(), x.b == "string"
    # T() = 7
    graph_q = TypesGraph()
    q_col0 = PredicateAddressing('Q', 'col0')
    x_var = Variable('x')
    a = SubscriptAddressing(x_var, 'a')
    b = SubscriptAddressing(x_var, 'b')
    graph_q.Connect(Equality(q_col0, x_var, (0, 0)))
    graph_q.Connect(FieldBelonging(x_var, a, (0, 0)))
    graph_q.Connect(FieldBelonging(x_var, b, (0, 0)))
    graph_q.Connect(Equality(a, PredicateAddressing('T', 'logica_value'), (0, 0)))
    graph_q.Connect(Equality(b, StringLiteral(), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph_q

    graph_t = TypesGraph()
    graph_t.Connect(Equality(PredicateAddressing('T', 'logica_value'), NumberLiteral(), (0, 0)))
    graphs['T'] = graph_t

    TypeInference(graphs).Infer()

    self.assertEqual(q_col0.type, RecordType({'a': number, 'b': string}, True))

  def test_when_plus_operator(self):
    # Q(x + y) :- T(x), T(y);
    graph_q = TypesGraph()
    q_col0 = PredicateAddressing('Q', 'col0')
    x_var_q = Variable('x')
    y_var_q = Variable('y')
    t_col0 = PredicateAddressing('T', 'col0')
    graph_q.Connect(Equality(q_col0, PredicateAddressing('+', 'logica_value'), (0, 0)))
    graph_q.Connect(Equality(x_var_q, PredicateAddressing('+', 'left'), (0, 0)))
    graph_q.Connect(Equality(y_var_q, PredicateAddressing('+', 'right'), (0, 0)))
    graph_q.Connect(Equality(x_var_q, t_col0, (0, 0)))
    graph_q.Connect(Equality(y_var_q, t_col0, (0, 0)))
    graphs = dict()
    graphs['Q'] = graph_q

    graph_t = TypesGraph()
    x_var_t = Variable('x')
    graph_t.Connect(Equality(PredicateAddressing('T', 'col0'), x_var_t, (0, 0)))
    graph_t.Connect(Equality(x_var_t, NumberLiteral(), (0, 0)))
    graphs['T'] = graph_t

    inferred_rules = TypeInference(graphs).Infer()

    self.assertEqual(q_col0.type, number)
    self.assertEqual(x_var_t.type, number)

  def test_when_opened_record_with_list(self):
    # Q(x, i) :- x.a == "range", x.b == Range(10), i in x.b
    graph = TypesGraph()
    graphs = dict()
    graphs['Q'] = graph
    x_var = Variable('x')
    i_var = Variable('i')
    a = SubscriptAddressing(x_var, 'a')
    b = SubscriptAddressing(x_var, 'b')
    graph.Connect(Equality(Variable('col0'), x_var, (0, 0)))
    graph.Connect(Equality(Variable('col1'), i_var, (0, 0)))
    graph.Connect(FieldBelonging(x_var, a, (0, 0)))
    graph.Connect(FieldBelonging(x_var, b, (0, 0)))
    graph.Connect(Equality(a, StringLiteral(), (0, 0)))
    graph.Connect(Equality(b, PredicateAddressing('Range', 'logica_value'), (0, 0)))
    graph.Connect(EqualityOfElement(b, i_var, (0, 0)))

    TypeInference(graphs).Infer()

    self.assertEqual(x_var.type, RecordType({'a': string, 'b': ListType(number)}, True))
    self.assertEqual(i_var.type, number)
