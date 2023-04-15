from typing import TypeVar, NewType, Dict


class Variable:
  def __init__(self, variable_name):
    self.variable_name = variable_name


class PredicateAddressing:
  def __init__(self, predicate_name: str, field: str):
    self.predicate_name = predicate_name
    self.field = field


class SubscriptAddressing:
  def __init__(self, subscript_field: str):
    self.subscript_field = subscript_field


PredicateFieldAddressing = TypeVar("PredicateFieldAddressing", PredicateAddressing, SubscriptAddressing)

Literal = NewType("Literal", object)
StringLiteral = NewType("StringLiteral", Literal)
NumberLiteral = NewType("NumberLiteral", Literal)
BooleanLiteral = NewType("BooleanLiteral", Literal)
NullLiteral = NewType("NullLiteral", Literal)
ListLiteral = NewType("ListLiteral", Literal)


class RecordLiteral(Literal):
  def __init__(self, fields: Dict[str, Literal]):
    self.fields = fields


Expression = TypeVar("Expression", Variable, Literal, PredicateFieldAddressing)
