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

from type_inference.intersection import Intersect, IntersectListElement
from type_inference.type_inference_exception import TypeInferenceException
from type_inference.types.variable_types import NumberType, StringType, ListType, AnyType, RecordType, AtomicType, \
  BoolType

number = NumberType()
string = StringType()
boolean = BoolType()
atomic = AtomicType()
list_of_nums = ListType(number)
list_of_strings = ListType(string)
any_type = AnyType()
empty_list = ListType(any_type)
opened_record = RecordType({'num': number, 'str': string}, True)
closed_record = RecordType({'num': number, 'str': string}, False)
opened_record_with_opened_record = RecordType({'num': number, 'opened_record': opened_record}, True)
opened_record_with_closed_record = RecordType({'num': number, 'closed_record': closed_record}, True)
closed_record_with_opened_record = RecordType({'num': number, 'opened_record': opened_record}, False)
closed_record_with_closed_record = RecordType({'num': number, 'closed_record': closed_record}, False)


class IntersectionTest(unittest.TestCase):
  @staticmethod
  def intersect_with_zero_bounds(intersect_func, type1, type2):
    return intersect_func(type1, type2, (0, 0))

  def test_success_when_intersect_equal_types(self):
    types = [number, string, boolean, list_of_nums, empty_list,
             opened_record, closed_record,
             opened_record_with_opened_record, opened_record_with_closed_record,
             closed_record_with_opened_record, closed_record_with_closed_record]
    for type in types:
      with self.subTest(type=type):
        result = self.intersect_with_zero_bounds(Intersect, type, type)
        self.assertEquals(result, type)

  def test_fail_when_intersect_not_equal_types(self):
    types = [number, string, boolean, list_of_nums,
             opened_record, closed_record,
             opened_record_with_opened_record, opened_record_with_closed_record,
             closed_record_with_opened_record, closed_record_with_closed_record]
    for first_type in types:
      for second_type in types:
        if first_type != second_type:
          with self.subTest(first_type=first_type, second_type=second_type):
            with self.assertRaises(TypeInferenceException):
              self.intersect_with_zero_bounds(Intersect, first_type, second_type)

  def test_success_when_intersect_list_element(self):
    result = self.intersect_with_zero_bounds(IntersectListElement, list_of_nums, number)
    self.assertEqual(result, number)

  def test_fail_when_intersect_list_element(self):
    with self.assertRaises(TypeInferenceException):
      self.intersect_with_zero_bounds(IntersectListElement, list_of_nums, string)

  def test_get_type_when_with_any(self):
    types = [number, string, list_of_nums, list_of_strings, empty_list]
    for t in types:
      with self.subTest(t=t):
        result = self.intersect_with_zero_bounds(Intersect, t, any_type)
        self.assertEqual(result, t)

  def test_get_list_with_type_when_list_with_any(self):
    result = self.intersect_with_zero_bounds(Intersect, list_of_nums, empty_list)
    self.assertEqual(result, ListType(number))

  def test_enrich_type_when_opened_records_with_extra(self):
    result = self.intersect_with_zero_bounds(Intersect, opened_record, opened_record_with_opened_record)
    self.assertEqual(result, RecordType({'num': number, 'str': string, 'opened_record': opened_record}, True))

  def test_fail_when_record_fields_are_different(self):
    record1 = RecordType({'a': NumberType(), 'b': StringType()}, True)
    record2 = RecordType({'a': NumberType(), 'b': NumberType()}, True)
    with self.assertRaises(TypeInferenceException):
      self.intersect_with_zero_bounds(Intersect, record1, record2)

  def test_success_when_atomic_types(self):
    cases = [number, string, atomic]
    for case in cases:
      with self.subTest(case=case):
        result = self.intersect_with_zero_bounds(Intersect, case, atomic)
        self.assertEqual(result, case)
