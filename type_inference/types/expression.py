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

from typing import Dict, List

from type_inference.built_in_functions_types import built_in_restrictions
from type_inference.types.variable_types import AnyType, NumberType, StringType, RecordType, ListType


class Expression:
  def __init__(self):
    self.type = AnyType()
    self.__class__.__hash__ = Expression.__hash__

  def __eq__(self, other):
    return isinstance(other, type(self))

  def __hash__(self):
    return hash(str(self))

  def __str__(self):
    return type(self).__name__


class PredicateAddressing(Expression):
  def __init__(self, predicate_name: str, field: str, predicate_id: int = 0):
    super().__init__()
    self.predicate_name = predicate_name
    self.field = field
    self.predicate_id = predicate_id

    if predicate_name in built_in_restrictions:
      self.type = built_in_restrictions[predicate_name][self.field]

  def __eq__(self, other):
    return super().__eq__(other) and \
           (self.predicate_name, self.field, self.predicate_id) == \
           (other.predicate_name, other.field, other.predicate_id)

  def __str__(self):
    return super().__str__() + f'({self.predicate_name}.{self.field})'


class SubscriptAddressing(Expression):
  def __init__(self, base: Expression, subscript_field: str):
    super().__init__()
    self.base = base
    self.subscript_field = subscript_field

  def __eq__(self, other):
    return super().__eq__(other) and self.subscript_field == other.subscript_field

  def __str__(self):
    return super().__str__() + f'{str(self.base)}.{self.subscript_field}'


class Variable(Expression):
  def __init__(self, variable_name):
    super().__init__()
    self.variable_name = variable_name

  def __eq__(self, other):
    return super().__eq__(other) and self.variable_name == other.variable_name

  def __str__(self):
    return super().__str__() + f'({self.variable_name})'


class Literal(Expression):
  pass


class StringLiteral(Literal):
  def __init__(self):
    super().__init__()
    self.type = StringType()


class NumberLiteral(Literal):
  def __init__(self):
    super().__init__()
    self.type = NumberType()


class BooleanLiteral(Literal):
  pass


class ListLiteral(Literal):
  def __init__(self, elements: List[Expression]):
    super().__init__()
    self.elements = elements
    if len(elements) > 0:
      self.type = ListType(elements[0].type)
    else:
      self.type = ListType(AnyType())

  def __eq__(self, other):
    return super().__eq__(other) and self.elements == self.elements

  def __str__(self):
    return super().__str__() + f'[{", ".join(map(str, self.elements))}]'


class NullLiteral(Literal):
  pass


class RecordLiteral(Literal):
  def __init__(self, fields: Dict[str, Expression]):
    super().__init__()
    self.fields = fields
    self.type = RecordType({name: expr.type for name, expr in fields.items()}, False)

  def __eq__(self, other):
    return super().__eq__(other) and self.fields == other.fields

  def __str__(self):
    fields = ', '.join(map(lambda t: f'{t[0]}: {t[1]}', sorted(self.fields.items(), key=lambda t: t[0])))
    return super().__str__() + f'({fields})'
