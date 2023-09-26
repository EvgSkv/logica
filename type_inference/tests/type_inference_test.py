#!/usr/bin/python
#
# Copyright 2023 Logica Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest

from type_inference.type_inference_service import TypeInference
from type_inference.types.edge import Equality, EqualityOfElement, FieldBelonging, PredicateArgument
from type_inference.types.expression import Variable, PredicateAddressing, NumberLiteral, SubscriptAddressing, \
  StringLiteral, RecordLiteral, ListLiteral
from type_inference.types.types_graph import TypesGraph
from type_inference.types.variable_types import NumberType, StringType, ListType, RecordType, AnyType, BoolType

number = NumberType()
string = StringType()


class TestTypeInference(unittest.TestCase):
  def test_when_num(self):
    # 'Q(x) :- x == 1'
    graph = TypesGraph()
    q_col0 = PredicateAddressing('Q', 'col0')
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
    q_col0 = PredicateAddressing('Q', 'col0')
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
    q_col0 = PredicateAddressing('Q', 'col0')
    graph.Connect(Equality(PredicateAddressing('Range', 'logica_value'), q_col0, (0, 0)))
    graph.Connect(Equality(PredicateAddressing('Range', 'col0'), NumberLiteral(), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    self.assertEqual(q_col0.type, ListType(number))

  def test_when_opened_record(self):
    # Q(x) :- x.a == 1, x.b == "string"
    graph = TypesGraph()
    q_col0 = PredicateAddressing('Q', 'col0')
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
    q_col0 = PredicateAddressing('Q', 'col0')
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
    graph.Connect(Equality(PredicateAddressing('Q', 'col0'), x_var, (0, 0)))
    graph.Connect(Equality(Variable('col1'), i_var, (0, 0)))
    graph.Connect(FieldBelonging(x_var, a, (0, 0)))
    graph.Connect(FieldBelonging(x_var, b, (0, 0)))
    graph.Connect(Equality(a, StringLiteral(), (0, 0)))
    graph.Connect(Equality(b, PredicateAddressing('Range', 'logica_value'), (0, 0)))
    graph.Connect(EqualityOfElement(b, i_var, (0, 0)))

    TypeInference(graphs).Infer()

    self.assertEqual(x_var.type, RecordType({'a': string, 'b': ListType(number)}, True))
    self.assertEqual(i_var.type, number)

  def test_when_closed_record(self):
    # Q({a: 1, b: "string"})
    graph = TypesGraph()
    q_col0 = PredicateAddressing('Q', 'col0')
    graph.Connect(Equality(q_col0, RecordLiteral({'a': NumberLiteral(), 'b': StringLiteral()}), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    self.assertEqual(q_col0.type, RecordType({'a': number, 'b': string}, False))
    self.assertEqual(q_col0.type.is_opened, False)

  def test_when_closed_record_with_closed_record_with_list(self):
    # Q({a: 1, b: {c: []}})
    graph = TypesGraph()
    q_col0 = PredicateAddressing('Q', 'col0')
    inner_record = RecordLiteral({'c': ListLiteral([])})
    graph.Connect(Equality(q_col0, RecordLiteral({'a': NumberLiteral(), 'b': inner_record}), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    expected = RecordType({'a': number, 'b': RecordType({'c': ListType(AnyType())}, False)}, False)
    self.assertEqual(q_col0.type, expected)

  def test_when_single_compare_operator(self):
    # Q(x < 2) :- x == 1;
    graph = TypesGraph()
    q_col0 = PredicateAddressing('Q', 'col0')
    x_var = Variable('x')
    graph.Connect(Equality(q_col0, PredicateAddressing('<', 'logica_value'), (0, 0)))
    graph.Connect(Equality(PredicateAddressing('<', 'left'), x_var, (0, 0)))
    graph.Connect(Equality(PredicateAddressing('<', 'right'), NumberLiteral(), (0, 0)))
    graph.Connect(Equality(x_var, NumberLiteral(), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    self.assertEqual(q_col0.type, BoolType())

  def test_when_two_compare_operators_with_different_types(self):
    # Q("h" < "a", 1 < 2);
    graph = TypesGraph()
    q_col0 = PredicateAddressing('Q', 'col0')
    q_col1 = PredicateAddressing('Q', 'col1')
    graph.Connect(Equality(q_col0, PredicateAddressing('<', 'logica_value'), (0, 0)))
    graph.Connect(Equality(PredicateAddressing('<', 'left'), StringLiteral(), (0, 0)))
    graph.Connect(Equality(PredicateAddressing('<', 'right'), StringLiteral(), (0, 0)))
    graph.Connect(Equality(q_col1, PredicateAddressing('<', 'logica_value', 1), (0, 0)))
    graph.Connect(Equality(PredicateAddressing('<', 'left', 1), NumberLiteral(), (0, 0)))
    graph.Connect(Equality(PredicateAddressing('<', 'right', 1), NumberLiteral(), (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    self.assertEqual(q_col0.type, BoolType())
    self.assertEqual(q_col1.type, BoolType())

  def test_when_compare_records_fields(self):
    # Q(y) :- x == {b: 5}, y in Range(10), y < x.b;
    graph = TypesGraph()
    q_col0 = PredicateAddressing('Q', 'col0')
    y_var = Variable('y')
    x_var = Variable('x')
    b = SubscriptAddressing(x_var, 'b')
    range_lv = PredicateAddressing('Range', 'logica_value')
    range_col0 = PredicateAddressing('Range', 'col0')
    graph.Connect(Equality(q_col0, y_var, (0, 0)))
    graph.Connect(FieldBelonging(x_var, b, (0, 0)))
    graph.Connect(Equality(x_var, RecordLiteral({'b': NumberLiteral()}), (0, 0)))
    graph.Connect(Equality(PredicateAddressing('<', 'left'), y_var, (0, 0)))
    graph.Connect(Equality(PredicateAddressing('<', 'right'), b, (0, 0)))
    graph.Connect(EqualityOfElement(range_lv, y_var, (0, 0)))
    graph.Connect(PredicateArgument(range_lv, range_col0, (0, 0)))
    graphs = dict()
    graphs['Q'] = graph

    TypeInference(graphs).Infer()

    self.assertEqual(q_col0.type, number)
