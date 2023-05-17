from typing import List, cast


class Type:
  pass


class AtomicType(Type):
  def __str__(self):
    return "atomic"

  def __hash__(self):
    return hash("atomic")


class NumberType(AtomicType):
  def __str__(self):
    return "number"

  def __hash__(self):
    return hash("number")


class StringType(AtomicType):
  def __str__(self):
    return "string"

  def __hash__(self):
    return hash("string")


class AnyType(Type):
  def __str__(self):
    return "any"

  def __hash__(self):
    return hash("any")


class ListType(Type):
  def __init__(self, element: Type):
    self.element = element

  def __str__(self):
    return f"[{self.element}]"

  def __hash__(self):
    return hash(f"[{self.element}]")


class Field:
  def __init__(self, name: str, type: Type):
    self.name = name
    self.type = type

  def __hash__(self):
    return hash((self.name, self.type))

  def __eq__(self, other):
    if not isinstance(other, Field):
      return False
    return self.name == other.name and self.type == other.type


class RecordType(Type):
  def __init__(self, fields: List[Field], is_opened: bool):
    self.fields = fields
    self.is_opened = is_opened

  def __eq__(self, other): # TODO TESTS !!! BITCHES
    if not isinstance(other, RecordType):
      return False

    other = cast(RecordType, other)

    if self.is_opened and other.is_opened:
      fields_set = set()
      for field in self.fields:
        fields_set.add(field.name)
      other_fields_set = set()
      for field in other.fields:
        other_fields_set.add(field.name)
      intersection = fields_set.intersection(other_fields_set)
      for field in intersection:
        if self.find_field_type(self.fields, field) != self.find_field_type(other.fields, field):
          return False
      return True

    if self.is_opened and not other.is_opened:
      return self.equal_open_close(self.fields, other.fields)

    if not self.is_opened and other.is_opened:
      return self.equal_open_close(other.fields, self.fields)

    fields_set = set()
    for field in self.fields:
      fields_set.add(field)
    other_fields_set = set()
    for field in other.fields:
      other_fields_set.add(field)
    intersection = fields_set.intersection(other_fields_set)

    return len(intersection) == len(fields_set)

  @staticmethod
  def equal_open_close(opened: List[Field], closed: List[Field]):
    for field in opened:
      if field not in closed:  # check eq
        return False
    return True

  @staticmethod
  def find_field_type(fields: List[Field], field_name):
    for field in fields:
      if field.name == field_name:
        return field.type


  def __hash__(self):
    pass
