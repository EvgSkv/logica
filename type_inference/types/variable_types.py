from typing import Dict, cast


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

  def __eq__(self, other):
    return isinstance(other, NumberType)


class StringType(AtomicType):
  def __str__(self):
    return "string"

  def __hash__(self):
    return hash("string")

  def __eq__(self, other):
    return isinstance(other, StringType)


class AnyType(Type):
  def __str__(self):
    return "any"

  def __hash__(self):
    return hash("any")

  def __eq__(self, other):
    return isinstance(other, AnyType)


class ListType(Type):
  def __init__(self, element: Type):
    self.element = element

  def __str__(self):
    return f"[{self.element}]"

  def __hash__(self):
    return hash(f"[{self.element}]")

  def __eq__(self, other):
    return isinstance(other, ListType) and self.element == other.element


class RecordType(Type):
  def __init__(self, fields: Dict[str, Type], is_opened: bool):
    self.fields = fields
    self.is_opened = is_opened

  def __eq__(self, other):
    if not isinstance(other, RecordType):
      return False

    other = cast(RecordType, other)

    if self.is_opened and other.is_opened:
      intersection = set(self.fields.keys()).intersection(set(other.fields.keys()))
      for field_name in intersection:
        if self.fields[field_name] != other.fields[field_name]:
          return False
      return True

    if self.is_opened and not other.is_opened:
      return self.equal_open_close(self.fields, other.fields)

    if not self.is_opened and other.is_opened:
      return self.equal_open_close(other.fields, self.fields)

    fields_set = set()
    for field in self.fields:
      fields_set.add((field, self.fields[field]))
    other_fields_set = set()
    for field in other.fields:
      other_fields_set.add((field, other.fields[field]))
    intersection = fields_set.intersection(other_fields_set)

    return len(intersection) == len(fields_set)

  @staticmethod
  def equal_open_close(opened: Dict[str, Type], closed: Dict[str, Type]):
    for field in opened:
      if field not in closed or opened[field] != closed[field]:  # check eq
        return False
    return True

  def __str__(self):
    return f"{{{', '.join(map(str, self.fields))}}}"


  def __hash__(self):
    return hash(f"{{{', '.join(map(str, self.fields))}}}")
    #todo used in __eq__
