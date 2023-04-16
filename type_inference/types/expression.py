from typing import Dict


class Expression:
  def __eq__(self, other):
    return isinstance(other, type(self))

  def __hash__(self):
    return hash(type(self))


class PredicateFieldAddressing(Expression):
  pass


class PredicateAddressing(PredicateFieldAddressing):
  def __init__(self, predicate_name: str, field: str):
    self.predicate_name = predicate_name
    self.field = field

  def __eq__(self, other):
    return super().__eq__(other) and self.predicate_name == other.predicate_name and self.field == other.field

  def __hash__(self):
    return hash((self.predicate_name, self.field))


class SubscriptAddressing(PredicateFieldAddressing):
  def __init__(self, subscript_field: str):
    self.subscript_field = subscript_field

  def __eq__(self, other):
    return super().__eq__(other) and self.subscript_field == other.subscript_field

  def __hash__(self):
    return hash(self.subscript_field)


class Variable(Expression):
  def __init__(self, variable_name):
    self.variable_name = variable_name

  def __eq__(self, other):
    return super().__eq__(other) and self.variable_name == other.variable_name

  def __hash__(self):
    return hash(self.variable_name)


class Literal(Expression):
  pass


class StringLiteral(Literal):
  pass


class NumberLiteral(Literal):
  pass


class BooleanLiteral(Literal):
  pass


class ListLiteral(Literal):
  pass


class NullLiteral(Literal):
  pass


class RecordLiteral(Literal):
  def __init__(self, fields: Dict[str, Literal]):
    self.fields = fields

  def __eq__(self, other):
    return super().__eq__(other) and self.fields == other.fields

  def __hash__(self):
    return hash(tuple(sorted(self.fields.items())))
