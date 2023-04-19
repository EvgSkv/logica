import sys

from parser_py import parse
from type_inference.types.types_graph import TypesGraph


def traverse_tree(rule):
  types_graph = TypesGraph()

  for field in rule["head"]["record"]["field_value"]:
    pass

  for conjunct in rule["body"]["conjunction"]["conjunct"]:
    # todo: fill types_graph by matching conject type - separate task
    pass

  return types_graph


def run(raw_program: str):
  parsed = parse.ParseFile(raw_program)
  graphs = dict()

  for rule in parsed["rule"]:
    graphs[rule["head"]["predicate_name"]] = traverse_tree(rule)

  # todo: use this result - separate task


if __name__ == '__main__':
  run(sys.argv[1])
