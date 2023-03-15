import sys

from parser_py import parse
from type_inference.types import TypesGraph


def traverse_tree(rule):
  types_graph = TypesGraph()

  for conjunct in rule["body"]["conjunction"]["conjunct"]:
    # todo: fill types_graph by matching conject type - separate task
    pass

  return types_graph


def run(raw_program: str):
  parsed = parse.ParseFile(raw_program)

  for rule in parsed["rule"]:
    # todo: use this result - separate task
    types_graph = traverse_tree(rule)


if __name__ == '__main__':
  run(sys.argv[1])
