from typing import Dict, List


class Expression:
  def __eq__(self, other):
    return isinstance(other, type(self))

  def __hash__(self):
    return hash(type(self))

  def __str__(self):
    return type(self).__name__


class PredicateFieldAddressing(Expression):
  pass


class PredicateAddressing(PredicateFieldAddressing):
  def __init__(self, predicate_name: str, field: str):
    super().__init__()
    self.predicate_name = predicate_name
    self.field = field

  def __eq__(self, other):
    return super().__eq__(other) and self.predicate_name == other.predicate_name and self.field == other.field

  def __hash__(self):
    return hash((self.predicate_name, self.field))

  def __str__(self):
    return super().__str__() + f'({self.predicate_name}.{self.field})'


class SubscriptAddressing(PredicateFieldAddressing):
  def __init__(self, base: Expression, subscript_field: str):
    super().__init__()
    self.base = base
    self.subscript_field = subscript_field

  def __eq__(self, other):
    return super().__eq__(other) and self.subscript_field == other.subscript_field

  def __hash__(self):
    return hash(self.subscript_field)

  def __str__(self):
    return super().__str__() + f'{str(self.base)}.{self.subscript_field}'


class Variable(Expression):
  def __init__(self, variable_name):
    self.variable_name = variable_name

  def __eq__(self, other):
    return super().__eq__(other) and self.variable_name == other.variable_name

  def __hash__(self):
    return hash(self.variable_name)

  def __str__(self):
    return super().__str__() + f'({self.variable_name})'


class Literal(Expression):
  pass


class StringLiteral(Literal):
  pass


class NumberLiteral(Literal):
  pass


class BooleanLiteral(Literal):
  pass


class ListLiteral(Literal):
  def __init__(self, elements: List[Expression]):
    self.elements = elements

  def __eq__(self, other):
    return super().__eq__(other) and self.elements == self.elements


class NullLiteral(Literal):
  pass


class RecordLiteral(Literal):
  def __init__(self, fields: Dict[str, Expression]):
    self.fields = fields

  def __eq__(self, other):
    return super().__eq__(other) and self.fields == other.fields

  def __hash__(self):
    return hash(tuple(sorted(self.fields.items())))

  def __str__(self):
    fields = ", ".join(map(str, self.fields.items()))
    return super().__str__() + f'({fields})'
