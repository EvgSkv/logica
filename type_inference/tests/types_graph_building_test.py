#!/usr/bin/python
#
# Copyright 2023 Logica
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

from parser_py import parse
from type_inference.types import edge, expression
from type_inference.types_graph_builder import TypesGraphBuilder


class TestTypesGraphBuilding(unittest.TestCase):
  def test_when_connection_with_other_predicates(self):
    s = 'Q(x) :- T(x), Num(x)'
    parsed = parse.ParseFile(s)

    graph = TypesGraphBuilder().Run(parsed)['Q']
    edges = graph.ToEdgesSet()

    expected = [edge.Equality(expression.PredicateAddressing('Q', 'col0'), expression.Variable('x'), (0, 0)),
                edge.Equality(expression.Variable('x'), expression.PredicateAddressing('T', 'col0'), (0, 0)),
                edge.Equality(expression.Variable('x'), expression.PredicateAddressing('Num', 'col0'), (0, 0))]

    self.assertCountEqual(edges, expected)

  def test_when_plus_operator(self):
    s = 'Q(x + y) :- T(x), T(y);'
    parsed = parse.ParseFile(s)

    graph = TypesGraphBuilder().Run(parsed)['Q']
    edges = graph.ToEdgesSet()

    x_var = expression.Variable('x')
    y_var = expression.Variable('y')
    expected = [edge.Equality(expression.PredicateAddressing('Q', 'col0'),
                              expression.PredicateAddressing('+', 'logica_value'), (0, 0)),
                edge.PredicateArgument(expression.PredicateAddressing('+', 'logica_value'),
                                       expression.PredicateAddressing('+', 'left'), (0, 0)),
                edge.PredicateArgument(expression.PredicateAddressing('+', 'logica_value'),
                                       expression.PredicateAddressing('+', 'right'), (0, 0)),
                edge.Equality(x_var, expression.PredicateAddressing('+', 'left'), (0, 0)),
                edge.Equality(y_var, expression.PredicateAddressing('+', 'right'), (0, 0)),
                edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)),
                edge.Equality(y_var, expression.PredicateAddressing('T', 'col0'), (0, 0))]

    self.assertCountEqual(edges, expected)

  def test_when_str(self):
    s = 'Q(x) :- T(x), T(y), Str(x), x == y;'
    parsed = parse.ParseFile(s)

    graph = TypesGraphBuilder().Run(parsed)['Q']
    edges = graph.ToEdgesSet()

    x_var = expression.Variable('x')
    y_var = expression.Variable('y')
    expected = [edge.Equality(expression.PredicateAddressing('Q', 'col0'), expression.Variable('x'), (0, 0)),
                edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)),
                edge.Equality(y_var, expression.PredicateAddressing('T', 'col0'), (0, 0)),
                edge.Equality(x_var, expression.PredicateAddressing('Str', 'col0'), (0, 0)),
                edge.Equality(x_var, y_var, (0, 0))]

    self.assertCountEqual(edges, expected)

  def test_when_concat_operator(self):
    s = 'Q(x ++ y) :- T(x), T(y);'
    parsed = parse.ParseFile(s)

    graph = TypesGraphBuilder().Run(parsed)['Q']
    edges = graph.ToEdgesSet()

    x_var = expression.Variable('x')
    y_var = expression.Variable('y')
    expected = [edge.Equality(expression.PredicateAddressing('Q', 'col0'),
                              expression.PredicateAddressing('++', 'logica_value'), (0, 0)),
                edge.PredicateArgument(expression.PredicateAddressing('++', 'logica_value'),
                                       expression.PredicateAddressing('++', 'left'), (0, 0)),
                edge.PredicateArgument(expression.PredicateAddressing('++', 'logica_value'),
                                       expression.PredicateAddressing('++', 'right'), (0, 0)),
                edge.Equality(x_var, expression.PredicateAddressing('++', 'left'), (0, 0)),
                edge.Equality(y_var, expression.PredicateAddressing('++', 'right'), (0, 0)),
                edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)),
                edge.Equality(y_var, expression.PredicateAddressing('T', 'col0'), (0, 0))]

    self.assertCountEqual(edges, expected)

  def test_when_in_operator(self):
    s = 'Q(y) :- T(x), y in x, Num(y);'
    parsed = parse.ParseFile(s)

    graph = TypesGraphBuilder().Run(parsed)['Q']
    edges = graph.ToEdgesSet()

    x_var = expression.Variable('x')
    y_var = expression.Variable('y')
    expected = [edge.Equality(expression.PredicateAddressing('Q', 'col0'), y_var, (0, 0)),
                edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)),
                edge.Equality(y_var, expression.PredicateAddressing('Num', 'col0'), (0, 0)),
                edge.EqualityOfElement(x_var, y_var, (0, 0))]

    self.assertCountEqual(edges, expected)

  def test_when_record(self):
    s = 'Q(p: Str(y), q: z + w, s: x) :- T(x), y == x.a, z == x.b, w == x.c.d;'
    parsed = parse.ParseFile(s)

    graph = TypesGraphBuilder().Run(parsed)['Q']
    edges = graph.ToEdgesSet()

    p_var = expression.PredicateAddressing('Q', 'p')
    q_var = expression.PredicateAddressing('Q', 'q')
    s_var = expression.PredicateAddressing('Q', 's')
    y_var = expression.Variable('y')
    z_var = expression.Variable('z')
    w_var = expression.Variable('w')
    x_var = expression.Variable('x')

    expected = [edge.Equality(p_var, expression.PredicateAddressing('Str', 'logica_value'), (0, 0)),
                edge.PredicateArgument(expression.PredicateAddressing('Str', 'logica_value'),
                                       expression.PredicateAddressing('Str', 'col0'), (0, 0)),
                edge.Equality(y_var, expression.PredicateAddressing('Str', 'col0'), (0, 0)),
                edge.Equality(q_var, expression.PredicateAddressing('+', 'logica_value'), (0, 0)),
                edge.PredicateArgument(expression.PredicateAddressing('+', 'logica_value'),
                                       expression.PredicateAddressing('+', 'left'), (0, 0)),
                edge.PredicateArgument(expression.PredicateAddressing('+', 'logica_value'),
                                       expression.PredicateAddressing('+', 'right'), (0, 0)),
                edge.Equality(z_var, expression.PredicateAddressing('+', 'left'), (0, 0)),
                edge.Equality(w_var, expression.PredicateAddressing('+', 'right'), (0, 0)),
                edge.Equality(s_var, x_var, (0, 0)),
                edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)),
                edge.Equality(expression.SubscriptAddressing(x_var, 'a'), y_var, (0, 0)),
                edge.Equality(expression.SubscriptAddressing(x_var, 'b'), z_var, (0, 0)),
                edge.Equality(expression.SubscriptAddressing(expression.SubscriptAddressing(x_var, 'c'), 'd'), w_var,
                              (0, 0)),
                edge.FieldBelonging(x_var, expression.SubscriptAddressing(x_var, 'a'), (0, 0)),
                edge.FieldBelonging(x_var, expression.SubscriptAddressing(x_var, 'b'), (0, 0)),
                edge.FieldBelonging(x_var, expression.SubscriptAddressing(x_var, 'c'), (0, 0)),
                edge.FieldBelonging(expression.SubscriptAddressing(x_var, 'c'),
                                    expression.SubscriptAddressing(expression.SubscriptAddressing(x_var, 'c'), 'd'),
                                    (0, 0))]

    self.assertCountEqual(edges, expected)

  def test_when_named_columns(self):
    s = 'Q(a:, b:) :- T(x), T(y), a == x + y, b == x + y;'
    parsed = parse.ParseFile(s)

    graph = TypesGraphBuilder().Run(parsed)['Q']
    edges = graph.ToEdgesSet()

    x_var = expression.Variable('x')
    y_var = expression.Variable('y')
    a_var = expression.Variable('a')
    b_var = expression.Variable('b')
    expected = [edge.Equality(expression.PredicateAddressing('Q', 'a'), a_var, (0, 0)),
                edge.Equality(expression.PredicateAddressing('Q', 'b'), b_var, (0, 0)),
                edge.Equality(x_var, expression.PredicateAddressing('T', 'col0'), (0, 0)),
                edge.Equality(y_var, expression.PredicateAddressing('T', 'col0'), (0, 0)),
                edge.Equality(a_var, expression.PredicateAddressing('+', 'logica_value'), (0, 0)),
                edge.Equality(b_var, expression.PredicateAddressing('+', 'logica_value'), (0, 0)),
                edge.PredicateArgument(expression.PredicateAddressing('+', 'logica_value'),
                                       expression.PredicateAddressing('+', 'left'), (0, 0)),
                edge.PredicateArgument(expression.PredicateAddressing('+', 'logica_value'),
                                       expression.PredicateAddressing('+', 'right'), (0, 0)),
                edge.Equality(x_var, expression.PredicateAddressing('+', 'left'), (0, 0)),
                edge.Equality(y_var, expression.PredicateAddressing('+', 'right'), (0, 0))]

    self.assertCountEqual(edges, expected)
