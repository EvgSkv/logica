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

"""Platonic object checks whether a json-like Python object obeys schema.

Example:
  my_schema = PlatonicObject({"a": Num, "b": {"c": Str}})
  print(my_schema, {"a": 1, "b": {"c": "Hi!"}})
  # prints true, None.
  print(my_schema, {"a": "wow", "b": {"c": "Hi!", "d": "Bye!"}})
  # prints false for any of two reasons:
  #   type of a is incorrect,
  #   b has unexpected field.

Fields in records are never required, missing field is considered OK.
"""


class PlatonicAdherence:

  def __init__(self, the_object, success, error):
    self.the_object = the_object
    self.success = success
    self.error = error

  def __bool__(self):
    return not self.error
  
  def __str__(self):
    return self.error if self.error else 'OK'
  
  def Elements(self):
    return (self.the_object, self.success, self.error)


class PlatonicObject:
  """Platonic object which instances check schema."""
  def __init__(self, fields):
    self.fields = fields

  def __call__(self, x):
    if adherence := self.AdheredBy(x):
      return x
    assert False, 'Type error:' + str(adherence)

  def AdheredBy(self, record, path='',
               original_record=None) -> PlatonicAdherence:
    original_record = original_record or record  

    def MakeError(message):
      """Contextualized error message."""
      return 'Record %s, at path: %s encountered error: %s' % (
          original_record, path, message)

    if not isinstance(record, dict):
      return PlatonicAdherence(record, False, MakeError(
          'Expected record, but got not a dictionary.'))

    # Going over observed fields.
    for field_name, field_value in record.items():
      expected_type = self.fields.get(field_name, None)
      # If the field does not exist, then return error.
      if field_name not in self.fields:
        return PlatonicAdherence(
          record, False, MakeError('Unexpected field: %s' % field_name))
      
      if isinstance(expected_type, PlatonicObject):  # If field is an object.
        adherence = expected_type.AdheredBy(
            field_value, path=path + '.' + field_name,
            original_record=original_record)
        if not adherence:
          return adherence
      elif isinstance(expected_type, list):  # If field is a list.
        if not isinstance(field_value, list):
          return PlatonicAdherence(record, False,
                  MakeError(
                      'Field value %s was expected to be a list, got: %s.' % (
                          field_name, field_value)))
        [element_type] = expected_type
        for element in field_value:
          if isinstance(element_type, PlatonicObject):
            adherence = element_type.AdheredBy(
                element, path=path + '.' + field_name,
                original_record=original_record)
            if not adherence:
              return adherence
          else:
            assert False, MakeError('Unexpected element of list type: %s' % repr(element_type))
      else:
        assert False, MakeError('Bad type: %s' % expected_type)
    return PlatonicAdherence(record, True, None)

  def __str__(self):
    return '{%s}' % (
        ', '.join(
            '%s: %s' % (k, str(v))
            for k, v in self.fields.items()
        )
    )


  def __repr__(self):
    return self.__str__()


class Pod(PlatonicObject):
  """Platonic object for pods, i.e. numbers, strings, booleans."""
  def __init__(self, pod_type):
    self.pod_type = pod_type


  def AdheredBy(self, record, path='', original_record=None):
    original_record = original_record or record

    if isinstance(record, self.pod_type):
      return PlatonicAdherence(record, True, None)
    else:
      return PlatonicAdherence(
        record, False, '%s%s: Expected %s, got %s' % (
            original_record, path, self.pod_type.__name__, repr(record)))

  def __str__(self):
    return self.__class__.__name__ + '(' + str(self.pod_type.__name__) + ')'

  def __repr__(self):
    return self.__str__()


class NumericMeta:
  """Numeric metaclass.
  
  An instance of this class is Numeric type, usable as an argument of Pod.

  Numeric means integer or float.
  """
  def __instancecheck__(self, x):
    return isinstance(x, int) or isinstance(x, float)

  def __init__(self):
    self.__name__ = 'Num'


Int = Pod(int)
Str = Pod(str)
Float = Pod(float)
Bool = Pod(bool)
Num = Pod(NumericMeta())