from typing import Dict, List
from type_inference.types.variable_types import AnyType, NumberType, StringType, ListType, RecordType, Field
from collections import defaultdict

#region BUILT_IN
inferred_rules = defaultdict(dict)
number_type = NumberType()
string_type = StringType()
inferred_rules['Range']['col0'] = number_type
inferred_rules['Range']['logica_value'] = ListType(number_type)

inferred_rules['Num']['col0'] = number_type
inferred_rules['Num']['logica_value'] = number_type

inferred_rules['Str']['col0'] = string_type
inferred_rules['Str']['logica_value'] = string_type

inferred_rules['+']['left'] = number_type
inferred_rules['+']['right'] = number_type
inferred_rules['+']['logica_value'] = number_type

inferred_rules['++']['left'] = string_type
inferred_rules['++']['right'] = string_type
inferred_rules['++']['logica_value'] = string_type
#endregion

class Expression:
  def __init__(self):
    self.type = AnyType()

  def __eq__(self, other):
    return isinstance(other, type(self))

  def __hash__(self):
    return hash(type(self))

  def __str__(self):
    return type(self).__name__


class PredicateFieldAddressing(Expression):
  _predicates_counter = 0

  def __init__(self):
    super().__init__()
    self._id = PredicateFieldAddressing._predicates_counter
    PredicateFieldAddressing._predicates_counter += 1

  def __eq__(self, other):
    return super().__eq__(other) and self._id == other._id


class PredicateAddressing(PredicateFieldAddressing):
  def __init__(self, predicate_name: str, field: str):
    super().__init__()
    self.predicate_name = predicate_name
    self.field = field
    if predicate_name in inferred_rules:
      self.type = inferred_rules[predicate_name][field]

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
    super().__init__()
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
  def __init__(self):
    super().__init__()
    self.type = StringType()


class NumberLiteral(Literal):
  def __init__(self):
    super().__init__()
    self.type = NumberType()


class BooleanLiteral(Literal):
  pass


class ListLiteral(Literal):
  def __init__(self, elements: List[Expression]):
    super().__init__()
    self.elements = elements

  def __eq__(self, other):
    return super().__eq__(other) and self.elements == self.elements


class NullLiteral(Literal):
  pass


class RecordLiteral(Literal):
  def __init__(self, fields: Dict[str, Expression]):
    super().__init__()
    self.fields = fields
    self.type = RecordType([Field(name, expr.type) for name, expr in fields.items()], False) # todo {a: f(x)}

  def __eq__(self, other):
    return super().__eq__(other) and self.fields == other.fields

  def __hash__(self):
    return hash(tuple(sorted(self.fields.items())))

  def __str__(self):
    fields = ", ".join(map(str, self.fields.items()))
    return super().__str__() + f'({fields})'
