from typing import List


class Type:
  pass


class AtomicType(Type):
  pass


class NumberType(AtomicType):
  pass


class StringType(AtomicType):
  pass


class AnyType(Type):
  pass


class ListType(Type):
  def __init__(self, element: Type):
    self.element = element


class Field:
  def __init__(self, name: str, type: Type):
    self.name = name
    self.type = type


class Record(Type):
  def __init__(self, fields: List[Field], is_opened: bool):
    self.fields = fields
    self.is_opened = is_opened
