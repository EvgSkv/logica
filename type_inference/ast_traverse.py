from collections import defaultdict

from parser_py import parse
from type_inference.types.edge import Equality, EqualityOfElement, FieldBelonging, PredicateArgument
from type_inference.types.expression import StringLiteral, NumberLiteral, BooleanLiteral, NullLiteral, ListLiteral, \
  PredicateAddressing, SubscriptAddressing, Variable, RecordLiteral
from type_inference.types.types_graph import TypesGraph

bounds = (0, 0)  # todo calculate bounds


def get_literal_expression(types_graph: TypesGraph, literal: dict):
  if 'the_string' in literal:
    return StringLiteral()
  elif 'the_number' in literal:
    return NumberLiteral()
  elif 'the_bool' in literal:
    return BooleanLiteral()
  elif 'the_null' in literal:
    return NullLiteral()
  elif 'the_list' in literal:
    return ListLiteral([convert_expression(types_graph, expression) for expression in literal['the_list']['element']])


def fill_fields(predicate_name: str, types_graph: TypesGraph, fields: dict, result: PredicateAddressing = None):
  for field in fields['record']['field_value']:
    value = convert_expression(types_graph, field['value']['expression'])
    field_name = field['field']

    if isinstance(field_name, int):
      field_name = f'col{field_name}'

    predicate_field = PredicateAddressing(predicate_name, field_name)
    types_graph.Connect(Equality(predicate_field, value, bounds))

    if result:
      types_graph.Connect(PredicateArgument(result, predicate_field, bounds))


def convert_expression(types_graph: TypesGraph, expression: dict):
  if 'literal' in expression:
    return get_literal_expression(types_graph, expression['literal'])

  if 'variable' in expression:
    return Variable(expression['variable']['var_name'])

  if 'call' in expression:
    call = expression['call']
    predicate_name = call['predicate_name']
    result = PredicateAddressing(predicate_name, 'logica_value')
    fill_fields(predicate_name, types_graph, call, result)
    return result

  if 'subscript' in expression:
    subscript = expression['subscript']
    record = convert_expression(types_graph, subscript['record'])
    field = subscript['subscript']['literal']['the_symbol']['symbol']
    result = SubscriptAddressing(record, field)
    types_graph.Connect(FieldBelonging(record, result, bounds))
    return result

  if 'record' in expression:
    record = expression['record']
    field_value = record['field_value']
    return RecordLiteral(
      {field['field']: convert_expression(types_graph, field['value']['expression']) for field in field_value})

  if 'implication' in expression:
    implication = expression['implication']
    # todo return and handle list
    # return [convert_expression(types_graph, i['consequence']) for i in implication['if_then']] + \
    #        [convert_expression(types_graph, implication['otherwise'])]

    # todo handle conditions
    return convert_expression(types_graph, implication['otherwise'])


def process_predicate(types_graph: TypesGraph, value: dict):
  predicate_name = value['predicate_name']
  fill_fields(predicate_name, types_graph, value)


def fill_field(types_graph: TypesGraph, predicate_name: str, field: dict):
  field_name = field['field']

  if isinstance(field_name, int):
    field_name = f'col{field_name}'

  variable = PredicateAddressing(predicate_name, field_name)

  if 'aggregation' in field['value']:
    value = convert_expression(types_graph, field['value']['aggregation']['expression'])
    types_graph.Connect(Equality(variable, value, bounds))
    return

  if 'expression' in field['value']:
    value = convert_expression(types_graph, field['value']['expression'])
    types_graph.Connect(Equality(variable, value, bounds))
    return

  raise NotImplementedError(field)


def fill_conjunct(types_graph: TypesGraph, conjunct: dict):
  if 'unification' in conjunct:
    unification = conjunct['unification']
    left_hand_side = convert_expression(types_graph, unification['left_hand_side'])
    right_hand_side = convert_expression(types_graph, unification['right_hand_side'])
    types_graph.Connect(Equality(left_hand_side, right_hand_side, bounds))
  elif 'inclusion' in conjunct:
    inclusion = conjunct['inclusion']
    list_of_elements = convert_expression(types_graph, inclusion['list'])
    element = convert_expression(types_graph, inclusion['element'])
    types_graph.Connect(EqualityOfElement(list_of_elements, element, bounds))
  elif 'predicate' in conjunct:
    process_predicate(types_graph, conjunct['predicate'])
  else:
    raise NotImplementedError(conjunct)


def traverse_tree(predicate_name: str, rule: dict):
  types_graph = TypesGraph()

  for field in rule['head']['record']['field_value']:
    fill_field(types_graph, predicate_name, field)

  if 'body' in rule:
    for conjunct in rule['body']['conjunction']['conjunct']:
      fill_conjunct(types_graph, conjunct)

  return types_graph


def run(raw_program: str):
  parsed = parse.ParseFile(raw_program)
  graphs = defaultdict(lambda: TypesGraph())

  for rule in parsed['rule']:
    predicate_name = rule['head']['predicate_name']
    graphs[predicate_name] |= traverse_tree(predicate_name, rule)

  return graphs
