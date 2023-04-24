from typing import List


class Type:
  pass


class AtomicType(Type):
  def __str__(self):
    return "atomic"


class NumberType(AtomicType):
  def __str__(self):
    return "number"


class StringType(AtomicType):
  def __str__(self):
    return "string"


class AnyType(Type):
  def __str__(self):
    return "any"


class ListType(Type):
  def __init__(self, element: Type):
    self.element = element

  def __str__(self):
    return f"[{self.element}]"


class Field:
  def __init__(self, name: str, type: Type):
    self.name = name
    self.type = type


class RecordType(Type):
  def __init__(self, fields: List[Field], is_opened: bool):
    self.fields = fields
    self.is_opened = is_opened
