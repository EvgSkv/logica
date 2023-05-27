import unittest

from type_inference.intersection import Intersect, IntersectListElement
from type_inference.type_inference_exception import TypeInferenceException
from type_inference.types.variable_types import NumberType, StringType, ListType, AnyType, RecordType

number = NumberType()
string = StringType()
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

  def test_success_when_intersect_equal_types(self):
    types = [number, string, list_of_nums, empty_list,
             opened_record, closed_record,
             opened_record_with_opened_record, opened_record_with_closed_record,
             closed_record_with_opened_record, closed_record_with_closed_record]
    for type in types:
      with self.subTest(type=type):
        result = Intersect(type, type)
        self.assertEquals(result, type)

  def test_fail_when_intersect_not_equal_types(self):
    types = [number, string, list_of_nums,
             opened_record, closed_record,
             opened_record_with_opened_record, opened_record_with_closed_record,
             closed_record_with_opened_record, closed_record_with_closed_record]
    for first_type in types:
      for second_type in types:
        if first_type != second_type:
          with self.subTest(first_type=first_type, second_type=second_type):
            with self.assertRaises(TypeInferenceException):
              Intersect(first_type, second_type)

  def test_success_when_intersect_list_element(self):
    result = IntersectListElement(list_of_nums, number)
    self.assertEqual(result, number)

  def test_fail_when_intersect_list_element(self):
    with self.assertRaises(TypeInferenceException):
      IntersectListElement(list_of_nums, string)

  def test_get_type_when_with_any(self):
    types = [number, string, list_of_nums, list_of_strings, empty_list]
    for t in types:
      with self.subTest(t=t):
        result = Intersect(t, any_type)
        self.assertEqual(result, t)

  def test_get_list_with_type_when_list_with_any(self):
    result = Intersect(list_of_nums, empty_list)
    self.assertEqual(result, ListType(number))
