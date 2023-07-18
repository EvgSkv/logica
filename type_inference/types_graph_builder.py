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

from collections import defaultdict
from typing import Dict, Tuple, Union

from parser_py.parse import HeritageAwareString
from type_inference.types.edge import Equality, EqualityOfElement, FieldBelonging, PredicateArgument
from type_inference.types.expression import StringLiteral, NumberLiteral, BooleanLiteral, NullLiteral, ListLiteral, \
  PredicateAddressing, SubscriptAddressing, Variable, RecordLiteral, Literal, Expression
from type_inference.types.types_graph import TypesGraph


class TypesGraphBuilder:
  _predicate_usages: defaultdict
  _if_statements_counter: int
  _expressions_cache: dict

  def ResetInternalState(self):
    self._predicate_usages = defaultdict(lambda: 0)
    self._if_statements_counter = 0
    self._expressions_cache = {}

  def GetFromCacheOrAdd(self, expression: Expression):
    if expression not in self._expressions_cache:
      self._expressions_cache[expression] = expression

    return self._expressions_cache[expression]

  def Run(self, parsed_program: dict) -> Dict[str, TypesGraph]:
    self.ResetInternalState()
    graphs = defaultdict(lambda: TypesGraph())

    for rule in parsed_program['rule']:
      predicate_name = rule['head']['predicate_name']
      graphs[predicate_name] |= self.TraverseTree(predicate_name, rule)

    return graphs

  def TraverseTree(self, predicate_name: str, rule: dict) -> TypesGraph:
    types_graph = TypesGraph()

    for field in rule['head']['record']['field_value']:
      self.FillField(types_graph, predicate_name, field)

    if 'body' in rule:
      for conjunct in rule['body']['conjunction']['conjunct']:
        self.FillConjunct(types_graph, conjunct)

    return types_graph

  def FillField(self, types_graph: TypesGraph, predicate_name: str, field: dict):
    field_name = field['field']

    if isinstance(field_name, int):
      field_name = f'col{field_name}'

    variable = self.GetFromCacheOrAdd(
      PredicateAddressing(predicate_name, field_name, self._predicate_usages[predicate_name]))

    if 'aggregation' in field['value']:
      value, bounds = self.ConvertExpression(types_graph, field['value']['aggregation']['expression'])
      types_graph.Connect(Equality(variable, value, bounds))
      return

    if 'expression' in field['value']:
      value, bounds = self.ConvertExpression(types_graph, field['value']['expression'])
      types_graph.Connect(Equality(variable, value, bounds))
      return

    raise NotImplementedError(field)

  def FillConjunct(self, types_graph: TypesGraph, conjunct: dict):
    if 'unification' in conjunct:
      unification = conjunct['unification']
      left_hand_side, (left, _) = self.ConvertExpression(types_graph, unification['left_hand_side'])
      right_hand_side, (_, right) = self.ConvertExpression(types_graph, unification['right_hand_side'])
      types_graph.Connect(Equality(left_hand_side, right_hand_side, (left, right)))
    elif 'inclusion' in conjunct:
      inclusion = conjunct['inclusion']
      list_of_elements, (_, right) = self.ConvertExpression(types_graph, inclusion['list'])
      element, (left, _) = self.ConvertExpression(types_graph, inclusion['element'])
      types_graph.Connect(EqualityOfElement(list_of_elements, element, (left, right)))
    elif 'predicate' in conjunct:
      value = conjunct['predicate']
      predicate_name = value['predicate_name']
      logica_value = PredicateAddressing(predicate_name, 'logica_value', self._predicate_usages[predicate_name])
      self.FillFields(predicate_name, types_graph, value, logica_value)
      self._predicate_usages[predicate_name] += 1
    else:
      raise NotImplementedError(conjunct)

  def FillFields(self, predicate_name: str, types_graph: TypesGraph, fields: dict, result: PredicateAddressing) -> \
          Tuple[int, int]:
    total_min = None
    total_max = None

    for field in fields['record']['field_value']:
      value, bounds = self.ConvertExpression(types_graph, field['value']['expression'])
      total_min = MinIgnoringNone(total_min, bounds[0])
      total_max = MaxIgnoringNone(total_max, bounds[1])
      field_name = field['field']

      if isinstance(field_name, int):
        field_name = f'col{field_name}'

      predicate_field = PredicateAddressing(predicate_name, field_name, self._predicate_usages[predicate_name])
      types_graph.Connect(Equality(predicate_field, value, bounds))
      types_graph.Connect(PredicateArgument(result, predicate_field, bounds))

    return total_min, total_max

  def ConvertExpression(self, types_graph: TypesGraph, expression: dict) -> Tuple[Expression, Tuple[int, int]]:
    if 'literal' in expression:
      result, bounds = self.ConvertLiteralExpression(types_graph, expression['literal'])
    elif 'variable' in expression:
      value = expression['variable']['var_name']
      result, bounds = Variable(value), (value.start, value.stop)
    elif 'call' in expression:
      result, bounds = self.ConvertCallExpression(types_graph, expression['call'])
    elif 'subscript' in expression:
      result, bounds = self.ConvertSubscriptExpression(types_graph, expression['subscript'])
    elif 'record' in expression:
      result, bounds = self.ConvertRecordExpression(types_graph, expression['record']['field_value'])
    elif 'implication' in expression:
      result, bounds = self.ConvertImplicationExpression(types_graph, expression['implication'])
    else:
      raise NotImplementedError(expression)

    return self.GetFromCacheOrAdd(result), bounds

  def ConvertLiteralExpression(self, types_graph: TypesGraph, literal: dict) -> Tuple[Literal, Tuple[int, int]]:
    if 'the_string' in literal:
      string = literal['the_string']['the_string']
      return StringLiteral(), (string.start, string.stop)
    elif 'the_number' in literal:
      number = literal['the_number']['number']
      return NumberLiteral(), (number.start, number.stop)
    elif 'the_bool' in literal:
      boolean = literal['the_bool']['bool']
      return BooleanLiteral(), (boolean.start, boolean.stop)
    elif 'the_null' in literal:
      null = literal['the_null']['null']
      return NullLiteral(), (null.start, null.stop)
    elif 'the_list' in literal:
      total_min = None
      total_max = None
      elements = []

      for element in literal['the_list']['element']:
        expression, (left, right) = self.ConvertExpression(types_graph, element)
        elements.append(expression)
        total_min = MinIgnoringNone(total_min, left)
        total_max = MinIgnoringNone(total_max, right)

      return ListLiteral(elements), (total_min - 1, total_max + 1)

  def ConvertCallExpression(self, types_graph: TypesGraph, call: dict):
    predicate_name = call['predicate_name']
    result = self.GetFromCacheOrAdd(
      PredicateAddressing(predicate_name, 'logica_value', self._predicate_usages[predicate_name]))
    bounds = self.FillFields(predicate_name, types_graph, call, result)
    self._predicate_usages[predicate_name] += 1
    return result, self.MoveBoundsAccordingToPredicateNameType(bounds, predicate_name)

  def ConvertSubscriptExpression(self, types_graph: TypesGraph, subscript: dict):
    record, (left, _) = self.ConvertExpression(types_graph, subscript['record'])
    field = subscript['subscript']['literal']['the_symbol']['symbol']
    result = self.GetFromCacheOrAdd(SubscriptAddressing(record, field))
    bounds = (left, field.stop)
    types_graph.Connect(FieldBelonging(record, result, bounds))
    return result, bounds

  def ConvertRecordExpression(self, types_graph: TypesGraph, field_value: dict):
    fields = {}
    total_min, total_max = None, None

    for field in field_value:
      expression, (left, right) = self.ConvertExpression(types_graph, field['value']['expression'])
      fields[field['field']] = expression
      total_min = MinIgnoringNone(total_min, left)
      total_max = MaxIgnoringNone(total_max, right)

    return RecordLiteral(fields), (total_min - 1, total_max + 1)

  def ConvertImplicationExpression(self, types_graph: TypesGraph, implication: dict):
    inner_variable = Variable(f'_IfNode{self._if_statements_counter}')
    self._if_statements_counter += 1
    otherwise, (common_left, common_right) = self.ConvertExpression(types_graph, implication['otherwise'])
    types_graph.Connect(Equality(inner_variable, otherwise, (common_left, common_right)))

    for i in implication['if_then']:
      self.ConvertExpression(types_graph, i['condition'])
      value, (left, right) = self.ConvertExpression(types_graph, i['consequence'])
      types_graph.Connect(Equality(inner_variable, value, (left, right)))
      common_left = MinIgnoringNone(common_left, left)
      common_right = MinIgnoringNone(common_right, right)

    return inner_variable, (common_left, common_right)

  def MoveBoundsAccordingToPredicateNameType(self, bounds: Tuple[int, int],
                                             predicate_name: Union[str, HeritageAwareString]) -> Tuple[int, int]:
    if isinstance(predicate_name, HeritageAwareString):
      return MinIgnoringNone(bounds[0], predicate_name.start), MaxIgnoringNone(bounds[1], predicate_name.stop)

    return bounds


def MinIgnoringNone(left: Union[int, None], right: int) -> int:
  return min(left, right) if left else right


def MaxIgnoringNone(left: Union[int, None], right: int) -> int:
  return max(left, right) if left else right
