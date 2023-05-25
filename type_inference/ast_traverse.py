from json import dumps
from collections import defaultdict

from parser_py import parse
from type_inference.types.edge import Equality, EqualityOfElement, FieldBelonging, PredicateArgument
from type_inference.types.expression import StringLiteral, NumberLiteral, BooleanLiteral, NullLiteral, ListLiteral, \
  PredicateAddressing, SubscriptAddressing, Variable, RecordLiteral
from type_inference.types.types_graph import TypesGraph

bounds = (0, 0)  # todo calculate bounds


def get_literal_expression(types_graph: TypesGraph, literal: dict):
  if "the_string" in literal:
    return StringLiteral()
  elif "the_number" in literal:
    return NumberLiteral()
  elif "the_bool" in literal:
    return BooleanLiteral()
  elif "the_null" in literal:
    return NullLiteral()
  elif "the_list" in literal:
    return ListLiteral([convert_expression(types_graph, expression) for expression in literal["the_list"]["element"]])


def fill_fields(predicate_name: str, types_graph: TypesGraph, fields: dict, result: PredicateAddressing = None):
  for field in fields["record"]["field_value"]:
    value = convert_expression(types_graph, field["value"]["expression"])
    predicate_field = PredicateAddressing(predicate_name, field["field"])
    types_graph.connect(Equality(predicate_field, value, bounds))

    if result:
      types_graph.connect(PredicateArgument(result, predicate_field, bounds))


def convert_expression(types_graph: TypesGraph, expression: dict):
  if "literal" in expression:
    return get_literal_expression(types_graph, expression["literal"])

  if "variable" in expression:
    return Variable(expression["variable"]["var_name"])

  if "call" in expression:
    call = expression["call"]
    predicate_name = call["predicate_name"]
    result = PredicateAddressing(predicate_name, "logica_value")
    fill_fields(predicate_name, types_graph, call, result)
    return result

  if "subscript" in expression:
    subscript = expression["subscript"]
    record = convert_expression(types_graph, subscript["record"])
    field = subscript["subscript"]["literal"]["the_symbol"]["symbol"]
    result = SubscriptAddressing(record, field)
    types_graph.connect(FieldBelonging(record, result, bounds))
    return result

  if "record" in expression:
    record = expression["record"]
    field_value = record["field_value"]
    return RecordLiteral(
      {field["field"]: convert_expression(types_graph, field["value"]["expression"]) for field in field_value})

  if "implication" in expression:
    implication = expression["implication"]
    # todo return and handle list
    # return [convert_expression(types_graph, i["consequence"]) for i in implication["if_then"]] + \
    #        [convert_expression(types_graph, implication["otherwise"])]

    # todo handle conditions
    return convert_expression(types_graph, implication["otherwise"])


def process_predicate(types_graph: TypesGraph, value: dict):
  predicate_name = value["predicate_name"]
  fill_fields(predicate_name, types_graph, value)


def fill_field(types_graph: TypesGraph, field: dict):
  variable = Variable(field["field"])

  if "aggregation" in field["value"]:
    value = convert_expression(types_graph, field["value"]["aggregation"]["expression"])
    types_graph.connect(Equality(variable, value, bounds))
    return

  if "expression" in field["value"]:
    value = convert_expression(types_graph, field["value"]["expression"])
    types_graph.connect(Equality(variable, value, bounds))
    return

  raise NotImplementedError(field)


def fill_conjunct(types_graph: TypesGraph, conjunct: dict):
  if "unification" in conjunct:
    unification = conjunct["unification"]
    left_hand_side = convert_expression(types_graph, unification["left_hand_side"])
    right_hand_side = convert_expression(types_graph, unification["right_hand_side"])
    types_graph.connect(Equality(left_hand_side, right_hand_side, bounds))
  elif "inclusion" in conjunct:
    inclusion = conjunct["inclusion"]
    list_of_elements = convert_expression(types_graph, inclusion["list"])
    element = convert_expression(types_graph, inclusion["element"])
    types_graph.connect(EqualityOfElement(list_of_elements, element, bounds))
  elif "predicate" in conjunct:
    process_predicate(types_graph, conjunct["predicate"])
  else:
    raise NotImplementedError(conjunct)


def traverse_tree(rule: dict):
  types_graph = TypesGraph()

  for field in rule["head"]["record"]["field_value"]:
    fill_field(types_graph, field)

  if "body" in rule:
    for conjunct in rule["body"]["conjunction"]["conjunct"]:
      fill_conjunct(types_graph, conjunct)

  return types_graph


def run(raw_program: str):
  parsed = parse.ParseFile(raw_program)
  graphs = defaultdict(lambda: TypesGraph())

  for rule in parsed["rule"]:
    predicate_name = rule["head"]["predicate_name"]
    graphs[predicate_name] |= traverse_tree(rule)

  return graphs


def build_graphs_for_rule_and_print(rule: str):
  print(rule)

  try:
    graphs = run(rule)

    for predicate_name, graph in graphs.items():
      print(predicate_name)
      print(dumps(graph.to_serializable_edges_list(), indent=2))
      print()
  except NotImplementedError:
    print("Can't build graph of types for this rule yet :(")
    print()


if __name__ == '__main__':
  test_rules = [
    'Q(x:) :- x == {a: 1, b: 10, c: {c: "Hello"}};',
    "Test(x:, y:) :- x in l, l == [0, 0.5, 1.0, 1.5, 2.0], y == 3 - x;",
    """
StructureExtractionTest(x:, w:) :-
  StructureTest(a:),
  x == a.x,
  w == a.z.w;""",
    "ByRoleCount(role:, count? += 1) distinct :- Employee(role:);",
    """
Awards(person_id: awardee_id, person_name: awardee_name, number_of_awards? += 1, awards? List= award) distinct :-
  db.award(awardee_id:, awardee_name:, award:);""",
    """Q(x:) :- x == (if 1 == 2 then 7 else 9);""",
    """
ShowbusinessStats(num_movies:,
                  num_people:,
                  num_bands:) :-
  num_movies += (1 :- db.movie()),
  num_people += (1 :- db.person()),
  num_bands += (1 :- db.rockband());""",
    "Q(x) :- T(x), Num(x);",
    "Q(x + y) :- T(x), T(y);",
    "Q(x) :- T(x), T(y), Str(x), x == y;",
    "Q(x ++ y) :- T(x), T(y);",
    "Q(y) :- T(x), y in x, Num(y);",
    "Q(Str(y)) :- T(x), y == x.a;",
    "Q(a:, b:) :- T(x), T(y), a == x * y, b == x + y;",
    "Q(p: Str(y), q: z + w, s: x) :- T(x), y == x.a, z == x.b, w == x.c.d;"
    "T(a, b) :- a.x == 2 * b, a.y.z == 3 * b;"
  ]

  for s in test_rules:
    build_graphs_for_rule_and_print(s.lstrip())
