from typing import List


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

  def __eq__(self, other):
    return isinstance(other, RecordType)


  def __hash__(self):
    pass
    # TODO
