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

from parser_py import parse
from type_inference.types.expression import Variable, PredicateAddressing, SubscriptAddressing
from type_inference.types_graph_builder import TypesGraphBuilder
from type_inference.type_inference_service import TypeInference
from type_inference.types.variable_types import NumberType, StringType, ListType, RecordType, AnyType

class IntegrationTypeInferenceTest(unittest.TestCase):
  def find_val(self, val, graph, check):
    for op in graph.ToEdgesSet():
      for v in op.vertices:
        if check(v, val):
          self.assertEqual(val.type, v.type)
          return
    raise Exception("Value not found")

  @staticmethod
  def check_var(v1, v2):
    return v1 == v2

  @staticmethod
  def check_predicate_addressing(p1, p2):
    return isinstance(p1, PredicateAddressing) and p1.predicate_name == p2.predicate_name and p1.field == p2.field

  @staticmethod
  def check_subscript_addressing(p1, p2):
    return isinstance(p1, SubscriptAddressing) and p1.subscript_field == p2.subscript_field and p1.base == p2.base

  def test_built_in_Num(self):
    raw_program = 'Q(x) :- Num(x)'
    parsed = parse.ParseFile(raw_program)
    graphs = dict()
    graphs['Q'] = TypesGraphBuilder().Run(parsed)['Q']
    TypeInference(graphs).Infer()
    var = Variable('x')
    var.type = NumberType()
    self.find_val(var, graphs['Q'], self.check_var)

  def test_built_in_range(self):
    raw_program = 'Q(x) :- x in Range(10)'
    parsed = parse.ParseFile(raw_program)
    graphs = dict()
    graphs['Q'] = TypesGraphBuilder().Run(parsed)['Q']
    TypeInference(graphs).Infer()
    var = Variable('x')
    var.type = NumberType()
    self.find_val(var, graphs['Q'], self.check_var)

  def test_unknown_type(self):
    raw_program = 'Q(x, y) :- x == y'
    parsed = parse.ParseFile(raw_program)
    graphs = dict()
    graphs['Q'] = TypesGraphBuilder().Run(parsed)['Q']
    TypeInference(graphs).Infer()
    var = Variable('x')
    var.type = AnyType()
    self.find_val(var, graphs['Q'], self.check_var)

  def test_three_predicates(self):
    raw = 'Q(x, y) :- T(y), Num(x), F(x); \n T(x) :- x == 10; \n F(x) :- x == 1; \n'
    parsed = parse.ParseFile(raw)
    res = TypesGraphBuilder().Run(parsed)
    TypeInference(res).Infer()
    var_x = Variable('x')
    var_y = Variable('y')
    var_x.type = NumberType()
    var_y.type = NumberType()
    self.find_val(var_x, res['Q'], self.check_var)
    self.find_val(var_x, res['T'], self.check_var)
    self.find_val(var_x, res['F'], self.check_var)
    self.find_val(var_y, res['Q'], self.check_var)

  def test_one_of_arguments_any(self):
    raw = 'Q(x, y) :- T(x), Num(x), F(x); \n T(x) :- x == 10; \n F(x) :- x == 1; \n'
    parsed = parse.ParseFile(raw)
    res = TypesGraphBuilder().Run(parsed)
    TypeInference(res).Infer()
    var_x = Variable('x')
    var_y = Variable('y')
    var_x.type = NumberType()
    var_y.type = AnyType()
    self.find_val(var_x, res['Q'], self.check_var)
    self.find_val(var_x, res['T'], self.check_var)
    self.find_val(var_x, res['F'], self.check_var)
    self.find_val(var_y, res['Q'], self.check_var)

  def test_when_list(self):
    raw = 'Q(Range(10));'
    parsed = parse.ParseFile(raw)
    res = TypesGraphBuilder().Run(parsed)
    TypeInference(res).Infer()
    predicate = PredicateAddressing('Q', 'col0')
    predicate.type = ListType(NumberType())
    self.find_val(predicate, res['Q'], self.check_predicate_addressing)

  def test_when_return_list(self):
    raw = 'F(x) :- x == Q(); \n Q() = Range(10);'
    parsed = parse.ParseFile(raw)
    res = TypesGraphBuilder().Run(parsed)
    TypeInference(res).Infer()
    var = Variable('x')
    var.type = ListType(NumberType())
    self.find_val(var, res['F'], self.check_var)

  def test_when_opened_record(self):
    raw = 'Q(x) :- x.a == 1, x.b == "string"'
    parsed = parse.ParseFile(raw)
    res = TypesGraphBuilder().Run(parsed)
    TypeInference(res).Infer()
    var = Variable('x')
    var.type = RecordType({'a': NumberType(), 'b': StringType()}, True)
    self.find_val(var, res['Q'], self.check_var)

  def test_when_opened_record_inside_open_record(self):
    raw = 'Q(x) :- x.a == 1, x.b.c == "string", x.b.a == 1;'
    parsed = parse.ParseFile(raw)
    res = TypesGraphBuilder().Run(parsed)
    TypeInference(res).Infer()
    var = Variable('x')
    var.type = RecordType({'a': NumberType(), 'b': RecordType({'c': StringType(), 'a': NumberType()}, True)}, True)
    self.find_val(var, res['Q'], self.check_var)

  def test_when_closed_record(self):
    raw = 'Q({a: 1, b: "string", c: {a :"str", b: 1}})'
    parsed = parse.ParseFile(raw)
    res = TypesGraphBuilder().Run(parsed)
    TypeInference(res).Infer()
    predicate = PredicateAddressing('Q', 'col0')
    predicate.type = RecordType({
      'a': NumberType(),
      'b': StringType(),
      'c': RecordType({'a': StringType(), 'b': NumberType()}, False)},
      False)
    self.find_val(predicate, res['Q'], self.check_predicate_addressing)

  def test_when_value_is_function_result(self):
    raw = 'Q(x) :- x.a == T(), x.b == "string"; \n T() = 777;'
    parsed = parse.ParseFile(raw)
    res = TypesGraphBuilder().Run(parsed)
    TypeInference(res).Infer()
    var = Variable('x')
    var.type = RecordType({'a': NumberType(), 'b': StringType()}, True)
    self.find_val(var, res['Q'], self.check_var)

  def test_when_list_in_closed_record(self):
    raw = 'F(x) :- x == {b: 1, a: [1,2]};'
    parsed = parse.ParseFile(raw)
    res = TypesGraphBuilder().Run(parsed)
    TypeInference(res).Infer()
    var = Variable('x')
    var.type = RecordType({'a': ListType(NumberType()), 'b': NumberType()}, False)
    self.find_val(var, res['F'], self.check_var)
