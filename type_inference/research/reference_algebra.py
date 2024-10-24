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

if '.' not in __package__:
  from common import color
else:
  try:
    from ...common import color
  except:
    from common import color


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
    if (isinstance(self[0], dict) and
        isinstance(self[1], dict)):
      if isinstance(self[0],
                    ClosedRecord):
        a, b = self
      else:
        b, a = self
    elif self[1] == 'Singular':
      b, a = self
    else:
      a, b = self

    colored_t1 = color.Format('{warning}{t}{end}',
                              args_dict={'t': RenderType(a)})
    colored_t2 = color.Format('{warning}{t}{end}',
                              args_dict={'t': RenderType(b)})

    if (isinstance(a, ClosedRecord) and
        isinstance(b, OpenRecord) and
        list(b)[0] not in a.keys()):
      colored_e = color.Format(
        '{warning}{t}{end}', args_dict={'t': RenderType(list(b)[0])})
      return (
        f'is a record {colored_t1} and it does not have ' +
        f'field {colored_e}, which is addressed.'
      )
    if a == 'Singular':
      assert isinstance(b, list), 'Fatally incorrect singular error: %s' % b
      return (
        f'belongs to a list, but is implied to be {colored_t2}. '
        f'Logica has to follow existing DB practice (Posgres, BigQuery) '
        f'and disallow lists to be elements of lists. This includes '
        f'ArgMaxK and ArgMinK aggregations, as they build lists. '
        f'Kindly wrap your inner list into a single field '
        f'record.'
      )

    return (
      f'is implied to be {colored_t1} and ' +
      f'simultaneously {colored_t2}, which is impossible.')
  def __repr__(self):
    return str(self)

class TypeReference:
  def __init__(self, target):
    self.target = target
  
  def WeMustGoDeeper(self):
    return isinstance(self.target, TypeReference)

  def Target(self):
    result = self
    while result.WeMustGoDeeper():
      result = result.target
    return result.target

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
  
  def __str__(self):
    return str(self.target) + '@' + hex(id(self))

  def __repr__(self):
    return str(self)
  
  def CloseRecord(self):
    a = self
    while a.WeMustGoDeeper():
      a = a.target
    if isinstance(a.target, BadType):
      return
    assert isinstance(a.target, dict), a.target
    a.target = ClosedRecord(a.target)

def StrIntKey(x):
  k, v = x
  if isinstance(k, str):
    return (k, v)
  if isinstance(k, int):
    return ('%03d' % k, v)
  assert False, 'x:%s' % str(x)
  
def RenderType(t):
  if isinstance(t, str):
    return t
  if isinstance(t, list):
    return '[%s]' % RenderType(t[0])
  if isinstance(t, dict):
    return '{%s}' % ', '.join('%s: %s' % (k, RenderType(v))
                              for k, v in sorted(t.items(), key=StrIntKey))
  if isinstance(t, tuple):
    return '(%s != %s)' % (RenderType(t[0]), RenderType(t[1]))
  assert False, type(t)

def ConcreteType(t):
  if isinstance(t, TypeReference):
    return t.Target()
  assert (isinstance(t, BadType) or
          isinstance(t, list) or
          isinstance(t, dict) or
          isinstance(t, str))
  return t

def VeryConcreteType(t, upward=None):
  upward = upward or set()
  if id(t) in upward:
    return BadType(('...', '...'))
  else:
    upward = upward | set([id(t)])

  c = ConcreteType(t)
  if isinstance(c, BadType):
    return BadType(VeryConcreteType(e, upward) for e in c)
  if isinstance(c, str):
    return c
  
  if isinstance(c, list):
    return [VeryConcreteType(e, upward) for e in c]
  
  if isinstance(c, dict):
    return type(c)({f: VeryConcreteType(v, upward) for f, v in c.items()})
  
  assert False


def IsFullyDefined(t):
  if t == 'Any':
    return False
  if t == 'Singular':
    return False
  if t == 'Sequential':
    return False
  if isinstance(t, str):
    return True
  if isinstance(t, BadType):
    return False
  if isinstance(t, list):
    [e] = t
    return IsFullyDefined(e)
  if isinstance(t, dict):
    return all(IsFullyDefined(v) for v in t.values())
  assert False


def Rank(x):
  """Rank of the type, arbitrary order for sorting."""
  x = ConcreteType(x)
  if isinstance(x, BadType):  # Tuple means error.
    return -1
  if x == 'Any':
    return 0
  if x == 'Singular':
    return 1
  if x == 'Sequential':
    return 2
  if x == 'Num':
    return 3
  if x == 'Str':
    return 4
  if x == 'Bool':
    return 5
  if x == 'Time':
    return 6
  if isinstance(x, list):
    return 7
  if isinstance(x, OpenRecord):
    return 8
  if isinstance(x, ClosedRecord):
    return 9
  assert False, 'Bad type: %s' % x


def Incompatible(a, b):
  return BadType((a, b))


def Unify(a, b):
  """Unifies type reference a with type reference b."""
  original_a = a
  original_b = b
  while a.WeMustGoDeeper():
    a = a.target
  while b.WeMustGoDeeper():
    b = b.target
  if original_a != a:
    original_a.target = a
  if original_b != b:
    original_b.target = b
  if id(a) == id(b):
    return
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
  
  if concrete_a == 'Singular':
    if isinstance(concrete_b, list):
      a.target, b.target = (
          Incompatible(a.target, b.target),
          Incompatible(b.target, a.target))
      return
    if concrete_b == 'Sequential':
      a.target = b
      b.target = 'Str'
      return
    a.target = b
    return

  if concrete_a == 'Sequential':
    if concrete_b in ('Str', 'Sequential') or isinstance(concrete_b, list):
      a.target = b
      return
    # Type error: a is incompatible with b.
    a.target, b.target = (
        Incompatible(a.target, b.target),
        Incompatible(b.target, a.target))
    return

  if concrete_a in ('Num', 'Str', 'Bool', 'Time'):
    if concrete_a == concrete_b:
      return  # It's all fine.
    # Type error: a is incompatible with b.
    a.target, b.target = (
        Incompatible(a.target, b.target),
        Incompatible(b.target, a.target))
    return

  if isinstance(concrete_a, list):
    if isinstance(concrete_b, list):
      a_element, b_element = concrete_a + concrete_b
      a_element = TypeReference.To(a_element)
      b_element = TypeReference.To(b_element)
      Unify(a_element, b_element)
      # TODO: Make this correct.
      if a_element.TargetTypeClassName() == 'BadType':
        a.target, b.target = (
          Incompatible(a.target, b.target),
          Incompatible(b.target, a.target))
        return
      a.target = [a_element]
      b.target = [b_element]
      return
    a.target, b.target = (
        Incompatible(a.target, b.target),
        Incompatible(b.target, a.target))
    
    return

  if isinstance(concrete_a, OpenRecord):
    if isinstance(concrete_b, OpenRecord):
      UnifyFriendlyRecords(a, b, OpenRecord)
      return
    if isinstance(concrete_b, ClosedRecord):
      if set(concrete_a) <= set(concrete_b):
        UnifyFriendlyRecords(a, b, ClosedRecord)
        return
      a.target, b.target = (
        Incompatible(a.target, b.target),
        Incompatible(b.target, a.target))
      return
    assert False

  if isinstance(concrete_a, ClosedRecord):
    if isinstance(concrete_b, ClosedRecord):
      if set(concrete_a) == set(concrete_b):
        UnifyFriendlyRecords(a, b, ClosedRecord)
        return
      a.target = Incompatible(a.target, b.target)
      b.target = Incompatible(b.target, a.target)
      return
    assert False
  assert False, (a, type(a), b, type(b))


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
  a.target = TypeReference(record_type(result))
  b.target = a.target


def UnifyListElement(a_list, b_element):
  """Analysis of expression `b in a`."""
  Unify(b_element, TypeReference.To('Singular'))
  b = TypeReference([b_element])
  Unify(a_list, b)


def UnifyRecordField(a_record, field_name, b_field_value):
  """Analysis of expresson `a.f = b`."""
  b = TypeReference(OpenRecord({field_name: b_field_value}))
  Unify(a_record, b)

class TypeStructureCopier:
  def __init__(self):
    self.id_to_reference = {}
  
  def CopyConcreteOrReferenceType(self, t):
    if isinstance(t, TypeReference):
      return self.CopyTypeReference(t)
    return self.CopyConcreteType(t)

  def CopyConcreteType(self, t):
    if isinstance(t, str):
      return t
    if isinstance(t, list):
      return [self.CopyConcreteOrReferenceType(e) for e in t]
    if isinstance(t, dict):
      c = type(t)
      return c({k: self.CopyConcreteOrReferenceType(v) for k, v in t.items()})
    if isinstance(t, BadType):
      return BadType((self.CopyConcreteOrReferenceType(t[0]),
                      self.CopyConcreteOrReferenceType(t[1])))
    assert False, (t, type(t))

  def CopyTypeReference(self, t):
    if id(t) not in self.id_to_reference:
      target = self.CopyConcreteOrReferenceType(t.target)
      n = TypeReference(target)
      self.id_to_reference[id(t)] = n
    return self.id_to_reference[id(t)]

def Revive(t):
  if isinstance(t, str):
    return TypeReference(t)
  if isinstance(t, dict):
    def ReviveKey(k):
      if k in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
        return int(k)
      return k
    return TypeReference(OpenRecord(
      {ReviveKey(k): Revive(v) for k, v in t.items()}))
  if isinstance(t, list):
    if len(t) == 1:
      return TypeReference(list(map(Revive, t)))
    elif len(t) == 2:
      return TypeReference(BadType(map(Revive, t)))
    else:
      assert False, t
  if isinstance(t, BadType):
    return TypeReference(BadType(map(Revive, t)))
  assert False, [type(t), t]