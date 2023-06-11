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

from collections import defaultdict

from parser_py import parse
from type_inference.types.edge import Equality, EqualityOfElement, FieldBelonging, PredicateArgument
from type_inference.types.expression import StringLiteral, NumberLiteral, BooleanLiteral, NullLiteral, ListLiteral, \
  PredicateAddressing, SubscriptAddressing, Variable, RecordLiteral
from type_inference.types.types_graph import TypesGraph

bounds = (0, 0)  # todo calculate bounds


def GetLiteralExpression(types_graph: TypesGraph, literal: dict):
  if 'the_string' in literal:
    return StringLiteral()
  elif 'the_number' in literal:
    return NumberLiteral()
  elif 'the_bool' in literal:
    return BooleanLiteral()
  elif 'the_null' in literal:
    return NullLiteral()
  elif 'the_list' in literal:
    return ListLiteral([ConvertExpression(types_graph, expression) for expression in literal['the_list']['element']])


def FillFields(predicate_name: str, types_graph: TypesGraph, fields: dict, result: PredicateAddressing = None):
  for field in fields['record']['field_value']:
    value = ConvertExpression(types_graph, field['value']['expression'])
    field_name = field['field']

    if isinstance(field_name, int):
      field_name = f'col{field_name}'

    predicate_field = PredicateAddressing(predicate_name, field_name)
    types_graph.Connect(Equality(predicate_field, value, bounds))

    if result:
      types_graph.Connect(PredicateArgument(result, predicate_field, bounds))


def ConvertExpression(types_graph: TypesGraph, expression: dict):
  if 'literal' in expression:
    return GetLiteralExpression(types_graph, expression['literal'])

  if 'variable' in expression:
    return Variable(expression['variable']['var_name'])

  if 'call' in expression:
    call = expression['call']
    predicate_name = call['predicate_name']
    result = PredicateAddressing(predicate_name, 'logica_value')
    FillFields(predicate_name, types_graph, call, result)
    return result

  if 'subscript' in expression:
    subscript = expression['subscript']
    record = ConvertExpression(types_graph, subscript['record'])
    field = subscript['subscript']['literal']['the_symbol']['symbol']
    result = SubscriptAddressing(record, field)
    types_graph.Connect(FieldBelonging(record, result, bounds))
    return result

  if 'record' in expression:
    record = expression['record']
    field_value = record['field_value']
    return RecordLiteral(
      {field['field']: ConvertExpression(types_graph, field['value']['expression']) for field in field_value})

  if 'implication' in expression:
    implication = expression['implication']
    # todo return and handle list
    # return [convert_expression(types_graph, i['consequence']) for i in implication['if_then']] + \
    #        [convert_expression(types_graph, implication['otherwise'])]

    # todo handle conditions
    return ConvertExpression(types_graph, implication['otherwise'])


def ProcessPredicate(types_graph: TypesGraph, value: dict):
  predicate_name = value['predicate_name']
  FillFields(predicate_name, types_graph, value)


def FillField(types_graph: TypesGraph, predicate_name: str, field: dict):
  field_name = field['field']

  if isinstance(field_name, int):
    field_name = f'col{field_name}'

  variable = PredicateAddressing(predicate_name, field_name)

  if 'aggregation' in field['value']:
    value = ConvertExpression(types_graph, field['value']['aggregation']['expression'])
    types_graph.Connect(Equality(variable, value, bounds))
    return

  if 'expression' in field['value']:
    value = ConvertExpression(types_graph, field['value']['expression'])
    types_graph.Connect(Equality(variable, value, bounds))
    return

  raise NotImplementedError(field)


def FillConjunct(types_graph: TypesGraph, conjunct: dict):
  if 'unification' in conjunct:
    unification = conjunct['unification']
    left_hand_side = ConvertExpression(types_graph, unification['left_hand_side'])
    right_hand_side = ConvertExpression(types_graph, unification['right_hand_side'])
    types_graph.Connect(Equality(left_hand_side, right_hand_side, bounds))
  elif 'inclusion' in conjunct:
    inclusion = conjunct['inclusion']
    list_of_elements = ConvertExpression(types_graph, inclusion['list'])
    element = ConvertExpression(types_graph, inclusion['element'])
    types_graph.Connect(EqualityOfElement(list_of_elements, element, bounds))
  elif 'predicate' in conjunct:
    ProcessPredicate(types_graph, conjunct['predicate'])
  else:
    raise NotImplementedError(conjunct)


def TraverseTree(predicate_name: str, rule: dict):
  types_graph = TypesGraph()

  for field in rule['head']['record']['field_value']:
    FillField(types_graph, predicate_name, field)

  if 'body' in rule:
    for conjunct in rule['body']['conjunction']['conjunct']:
      FillConjunct(types_graph, conjunct)

  return types_graph


def Run(raw_program: str):
  parsed = parse.ParseFile(raw_program)
  graphs = defaultdict(lambda: TypesGraph())

  for rule in parsed['rule']:
    predicate_name = rule['head']['predicate_name']
    graphs[predicate_name] |= TraverseTree(predicate_name, rule)

  return graphs
