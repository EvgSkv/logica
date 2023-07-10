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

# Type algebra working off of type references.

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


class TypeReference:
  def __init__(self, target):
    self.target = target
  
  def Target(self):
    result = self
    while isinstance(result, TypeReference):
      result = result.target
    return result

  def TargetTypeClassName(self):
    target = self.Target()
    return type(target).__name__

  @classmethod
  def To(cls, target):
    if isinstance(target, TypeReference):
      return target
    return TypeReference(target)
  
  def IsBadType(self):
    return isinstance(self.Target(), BadType)


def ConcreteType(t):
  if isinstance(t, TypeReference):
    return t.Target()
  assert (isinstance(t, BadType) or
          isinstance(t, list) or
          isinstance(t, dict) or
          isinstance(t, str))
  return t


def Rank(x):
  """Rank of the type, arbitrary order for sorting."""
  x = ConcreteType(x)
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


def Unify(a, b):
  """Unifies type reference a with type reference b."""
  assert isinstance(a, TypeReference)
  assert isinstance(b, TypeReference)
  concrete_a = ConcreteType(a)
  concrete_b = ConcreteType(b)

  if isinstance(concrete_a, BadType) or isinstance(concrete_b, BadType):
    return  # Do nothing.

  if Rank(concrete_a) > Rank(concrete_b):
    a, b = b, a
    concrete_a, concrete_b = concrete_b, concrete_a

  if concrete_a == 'Any':
    a.target = b
    return

  if a in ('Num', 'Str'):
    if a == b:
      return  # It's all fine.
    a.target = Incompatible(a, b)  # Type error: a is incompatible with b.
    b.target = Incompatible(a, b)

  if isinstance(a, list):
    if isinstance(b, list):
      a_element, b_element = a + b
      a_element = TypeReference.To(a_element)
      b_element = TypeReference.To(b_element)
      Unify(a_element, b_element)
      # TODO: Make this correct.
      if a_element.TargetTypeClassName() == 'BadType':
        a.target = BadType(a, b)
        b.target = BadType(a, b)
        return
      a.target = [a_element]
      b.target = [b_element]
      return
    a.target = BadType(a, b)
    b.target = BadType(b, a)
    return

  if isinstance(concrete_a, OpenRecord):
    if isinstance(concrete_b, OpenRecord):
      UnifyFriendlyRecords(a, b, OpenRecord)
      return
    if isinstance(concrete_b, ClosedRecord):
      if set(concrete_a) <= set(concrete_b):
        UnifyFriendlyRecords(a, b, ClosedRecord)
        return
      a.target = Incompatible(a, b)
      b.target = Incompatible(b, a)
    assert False

  if isinstance(a, ClosedRecord):
    if isinstance(b, ClosedRecord):
      if set(a) == set(b):
        return UnifyFriendlyRecords(a, b, ClosedRecord)
      a.target = Incompatible(a, b)
      b.target = Incompatible(b, a)
    assert False
  assert False


def UnifyFriendlyRecords(a, b, record_type):
  """Intersecting records assuming that their fields are compatible."""
  concrete_a = ConcreteType(a)
  concrete_b = ConcreteType(b)
  result = {}
  for f in set(concrete_a) | set(concrete_b):
    x = TypeReference.To('Any')
    if f in concrete_a:
      Unify(x, TypeReference.To(concrete_a[f]))
    if f in concrete_b:
      Unify(x, TypeReference.To(concrete_b[f]))
    if x.TargetTypeClassName() == 'BadType':  # Ooops, field type error.
      a.target = Incompatible(a, b)
      b.target = Incompatible(b, a)
    result[f] = x
  a.target = record_type(result)
  b.target = record_type(result)


def UnifyListElement(a_list, b_element):
  """Analysis of expression `b in a`."""
  b = TypeReference([b_element])
  Unify(a_list, b)

  # TODO: Prohibit lists of lists.


def IntersectRecordField(a_record, field_name, b_field_value):
  """Analysis of expresson `a.f = b`."""
  b = TypeReference(OpenRecord({field_name: b_field_value}))
  Unify(a_record, b)


