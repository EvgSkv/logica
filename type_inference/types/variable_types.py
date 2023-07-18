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

from typing import Dict


class Type:
  def __init__(self):
    self.__class__.__hash__ = Type.__hash__

  def __str__(self):
    return 'type'

  def __hash__(self):
    return hash(str(self))

  def __eq__(self, other):
    return isinstance(other, type(self))


class AtomicType(Type):
  def __str__(self):
    return 'atomic'


class NumberType(AtomicType):
  def __str__(self):
    return 'number'


class StringType(AtomicType):
  def __str__(self):
    return 'string'


class BoolType(Type):
  def __str__(self):
    return 'bool'


class AnyType(Type):
  def __str__(self):
    return 'any'


class ListType(Type):
  def __init__(self, element: Type):
    super().__init__()
    self.element = element

  def __str__(self):
    return f'[{self.element}]'

  def __eq__(self, other):
    return super().__eq__(other) and self.element == other.element


class RecordType(Type):
  def __init__(self, fields: Dict[str, Type], is_opened: bool):
    super().__init__()
    self.fields = fields
    self.is_opened = is_opened

  def __eq__(self, other):
    def EqualOpenToClose(opened: Dict[str, Type], closed: Dict[str, Type]):
      return all(field in closed and closed[field] == value for field, value in opened.items())

    if not super().__eq__(other):
      return False

    if self.is_opened and other.is_opened:
      intersection = set(self.fields.keys()).intersection(set(other.fields.keys()))
      return all(self.fields[field_name] == other.fields[field_name] for field_name in intersection)

    if self.is_opened and not other.is_opened:
      return EqualOpenToClose(self.fields, other.fields)

    if not self.is_opened and other.is_opened:
      return EqualOpenToClose(other.fields, self.fields)

    fields_set = set(self.fields.items())
    other_fields_set = set(other.fields.items())
    intersection = fields_set.intersection(other_fields_set)

    return len(intersection) == len(fields_set)

  def __str__(self):
    fields = ', '.join(map(lambda t: f'{t[0]}: {t[1]}', sorted(self.fields.items(), key=lambda t: t[0])))
    return f'{{{fields}}}'
