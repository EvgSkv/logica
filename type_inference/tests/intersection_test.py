import unittest

from type_inference.intersection import Intersect, IntersectListElement, IntersectFriendlyRecords
from type_inference.types.variable_types import NumberType, StringType, ListType, AnyType, RecordType
from type_inference.type_inference_exception import TypeInferenceException

number = NumberType()
string = StringType()
list_of_nums = ListType(number)
any_type = AnyType()
empty_list = ListType(any_type)
# opened_record = RecordType([Field()])

class IntersectionTest(unittest.TestCase):

  def test_success_when_intersect_equal_types(self):
    types = [number, string, list_of_nums, empty_list]
    for t in types:
      with self.subTest(t=t):
        result = Intersect(t, t)
        self.assertEquals(result, t)

  # def test_fail_when_intersect_not_equal_types(self):
  #   types = [number, string, list_of_nums, empty_list]
  #   for t1 in types:
  #     for t2 in types:
  #       if t1 != t2:
  #         with self.subTest(t1=t1, t2=t2):
  #           with self.assertRaises(TypeInferenceException):
  #             Intersect(t1, t2)

  def test_success_when_intersect_list_element(self):
    result = IntersectListElement(list_of_nums, number)
    self.assertEqual(result, number)
