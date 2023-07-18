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

from typing import Tuple, cast

from type_inference.type_inference_exception import TypeInferenceException
from type_inference.types.variable_types import AnyType, NumberType, StringType, ListType, RecordType, Type, AtomicType, \
  BoolType


def Rank(x):
  if isinstance(x, AnyType):
    return 0
  if isinstance(x, BoolType):
    return 1
  if isinstance(x, NumberType):
    return 2
  if isinstance(x, StringType):
    return 3
  if isinstance(x, AtomicType):
    return 4
  if isinstance(x, ListType):
    return 5
  if isinstance(x, RecordType):
    if x.is_opened:
      return 6
    return 7


def Intersect(a: Type, b: Type, bounds: Tuple[int, int]) -> Type:
  if Rank(a) > Rank(b):
    a, b = b, a

  if isinstance(a, AnyType):
    return b

  if isinstance(a, BoolType):
    if a == b:
      return a
    raise TypeInferenceException(a, b, bounds)

  if isinstance(a, AtomicType):
    if a == b or type(b) == AtomicType:
      return a
    raise TypeInferenceException(a, b, bounds)

  if isinstance(a, ListType):
    if isinstance(b, ListType):
      new_element = Intersect(a.element, b.element, bounds)
      return ListType(new_element)
    raise TypeInferenceException(a, b, bounds)

  a = cast(RecordType, a)
  b = cast(RecordType, b)
  if a.is_opened:
    if b.is_opened:
      return IntersectFriendlyRecords(a, b, True, bounds)
    else:
      if set(a.fields.keys()) <= set(b.fields.keys()):
        return IntersectFriendlyRecords(a, b, False, bounds)
      raise TypeInferenceException(a, b, bounds)
  else:
    if set(a.fields.keys()) == set(b.fields.keys()):
      return IntersectFriendlyRecords(a, b, False, bounds)
    raise TypeInferenceException(a, b, bounds)


def IntersectFriendlyRecords(a: RecordType, b: RecordType, is_opened: bool, bounds: Tuple[int, int]) -> RecordType:
  result = RecordType({}, is_opened)
  for name, f_type in b.fields.items():
    if name in a.fields:
      intersection = Intersect(f_type, a.fields[name], bounds)
      result.fields[name] = intersection
    else:
      result.fields[name] = f_type
  return result


def IntersectListElement(a_list: ListType, b_element: Type, bounds: Tuple[int, int]) -> Type:
  return Intersect(a_list.element, b_element, bounds)
