#!/usr/bin/python
#
# Copyright 2023 Google LLC
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


class OpenRecord(dict):
  def __str__(self):
    return '{%s, ...}' % str(dict(self))[1:-1]
  def __repr__(self):
    return str(self)


class ClosedRecord(dict):
  def __str__(self):
    return str(dict(self))
  def __repr__(self):
    return str(self)


class BadType(tuple):
  def __str__(self):
    return f'({self[0]} is incompatible with {self[1]})'
  def __repr__(self):
    return str(self)


def Rank(x):
  """Rank of the type, arbitrary order for sorting."""
  if isinstance(x, BadType):  # Tuple means error.
    return -1
  if x == 'Any':
    return 0
  if x == 'Num':
    return 1
  if x == 'Str':
    return 2
  if isinstance(x, list):
    return 3
  if isinstance(x, OpenRecord):
    return 4
  if isinstance(x, ClosedRecord):
    return 5
  assert False, 'Bad type: %s' % x


def Incompatible(a, b):
  return BadType((a, b))


def Intersect(a, b):
  """Intersection of types a and b."""
  if isinstance(a, BadType) or isinstance(b, BadType):
    return a

  if Rank(a) > Rank(b):
    a, b = b, a

  if a == 'Any':
    return b

  if a in ('Num', 'Str'):
    if a == b:
      return b
    return Incompatible(a, b)  # Type error: a is incompatible with b.

  if isinstance(a, list):
    if isinstance(b, list):
      a_element, b_element = a + b
      new_element = Intersect(a_element, b_element)
      if isinstance(new_element, BadType):
        return Incompatible(a, b)
      return [new_element]
    return Incompatible(a, b)

  if isinstance(a, OpenRecord):
    if isinstance(b, OpenRecord):
      return IntersectFriendlyRecords(a, b, OpenRecord)
    if isinstance(b, ClosedRecord):
      if set(a) <= set(b):
        return IntersectFriendlyRecords(a, b, ClosedRecord)
      return Incompatible(a, b)
    assert False

  if isinstance(a, ClosedRecord):
    if isinstance(b, ClosedRecord):
      if set(a) == set(b):
        return IntersectFriendlyRecords(a, b, ClosedRecord)
      return Incompatible(a, b)
    assert False
  assert False

def IntersectFriendlyRecords(a, b, record_type):
  """Intersecting records assuming that their fields are compatible."""
  result = {}
  for f in set(a) | set(b):
    x = Intersect(a.get(f, 'Any'), b.get(f, 'Any'))
    if isinstance(x, BadType):  # Ooops, field type error.
      return Incompatible(a, b)
    result[f] = x
  return record_type(result)

def IntersectListElement(a_list, b_element):
  """Analysis of expression `b in a`."""
  a_result = Intersect(a_list, [b_element])
  if isinstance(a_result, BadType):
    return (Incompatible(a_list, [b_element]), b_element)

  if isinstance(b_element, list):  # No lists of lists in BigQuery.
    return (a_result, Incompatible(b_element, 'NotAList'))

  [a_element] = a_result
  b_result = Intersect(b_element, a_element)
  return (a_result, b_result)

def IntersectRecordField(a_record, field_name, b_field_value):
  """Analysis of expresson `a.f = b`."""
  a_result = Intersect(a_record, OpenRecord({field_name: b_field_value}))
  if isinstance(a_result, BadType):
    return (a_result, b_field_value)
  b_result = Intersect(a_result[field_name], b_field_value)
  return (a_result, b_result)

