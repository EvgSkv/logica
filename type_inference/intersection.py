#!/usr/bin/python
#
# Copyright 2020 Google LLC
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

from typing import cast

from type_inference.type_inference_exception import TypeInferenceException
from type_inference.types.variable_types import AnyType, NumberType, StringType, ListType, RecordType, Type


def Rank(x):
  if isinstance(x, AnyType):
    return 0
  if isinstance(x, NumberType):
    return 1
  if isinstance(x, StringType):
    return 2
  if isinstance(x, ListType):
    return 3
  if isinstance(x, RecordType):
    if x.is_opened:
      return 4
    else:
      return 5


def Intersect(a: Type, b: Type) -> Type:
  if Rank(a) > Rank(b):
    a, b = b, a

  if isinstance(a, AnyType):
    return b

  if isinstance(a, NumberType) or isinstance(a, StringType):
    if a == b:
      return b
    raise TypeInferenceException()

  if isinstance(a, ListType):
    if isinstance(b, ListType):
      new_element = Intersect(a.element, b.element)
      return ListType(new_element)
    raise TypeInferenceException()

  a = cast(RecordType, a)
  b = cast(RecordType, b)
  if a.is_opened:
    if b.is_opened:
      return IntersectFriendlyRecords(a, b, True)
    else:
      if set(a.fields.keys()) <= set(b.fields.keys()):
        return IntersectFriendlyRecords(a, b, False)
      raise TypeInferenceException()
  else:
    if set(a.fields.keys()) == set(b.fields.keys()):
      return IntersectFriendlyRecords(a, b, False)
    raise TypeInferenceException()


def IntersectFriendlyRecords(a: RecordType, b: RecordType, is_opened: bool) -> RecordType:
  result = RecordType({}, is_opened)
  for name, f_type in b.fields.items():
    if name in a.fields:
      intersection = Intersect(f_type, a.fields[name])
      result.fields[name] = intersection
    else:
      result.fields[name] = f_type
  return result


def IntersectListElement(a_list: ListType, b_element: Type) -> Type:
  return Intersect(a_list.element, b_element)
