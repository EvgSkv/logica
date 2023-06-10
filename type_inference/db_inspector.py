import argparse
import sys
from typing import List, Set

from parser_py import parse
from type_inference.column_info import ColumnInfo
from type_inference.inspectors.sqlite_inspector import SQLiteInspector
from type_inference.logger import Logger


def get_predicates(rule: dict) -> Set[str]:
  conjuncts = []
  if 'body' in rule:
    body_conjuncts = rule['body']['conjunction']['conjunct']
    conjuncts.extend(body_conjuncts)
  if 'record' in rule['head']:
    head_conjuncts = rule['head']['record']['field_value']
    conjuncts.extend(head_conjuncts)

  predicates = set()
  for conjunct in conjuncts:
    fill_predicates_list(conjunct, predicates)

  return predicates


def fill_predicates_list(dictionary: dict, predicates: Set[str]):
  try:
    for key, value in dictionary.items():
      if key == 'predicate_name':
        predicates.add(value)
      else:
        fill_predicates_list(value, predicates)
  except AttributeError:
    pass


def inspect_table(name: str, inspector) -> List[ColumnInfo]:
  columns_info = inspector.get_columns(name)
  return [ColumnInfo(column['name'], name, column['type']) for column in columns_info]


def get_unknown_predicates(raw_program: str) -> Set[str]:
  parsed = parse.ParseFile(raw_program)
  rules = parsed['rule']
  defined_predicates_names = set([rule['head']['predicate_name'] for rule in rules])
  all_predicates = set()
  for rule in rules:
    all_predicates = all_predicates.union(get_predicates(rule))
  return all_predicates.difference(defined_predicates_names)


def run(raw_program: str):
  unknown_predicates = get_unknown_predicates(raw_program)

  if not unknown_predicates:
    return

  logger = Logger()
  # inspector = PostgresInspector('logica', 'logica', logger)
  inspector = SQLiteInspector('type_inference/logica.db', logger)

  for predicate in unknown_predicates:
    columns_info = inspector.TryGetColumnsInfo(predicate)
    for column in columns_info:
      print(str(column))


# Examples:
# Q(x, y, a) :- a == U(x), y == 1; A();
# Q(x, y) :- U(x), y == 1; A();
# StudentName(name:) :- students(name:);
# StudentName(name:) :- unknown_students(name:);
# Q(x: U(1), y: A()); A();
# Q(x: U(1), y: G()) :- V();
# Q(x: U(1));
# Q(a, b) :- a < b, a in Range(10), b in Range(10)

# Run
# python3 -m type_inference.db_inspector 'StudentName(name:) :- students(name:);'


if __name__ == '__main__':
  args_parser = argparse.ArgumentParser()
  args_parser.add_argument('-p', '--program', required=True)
  args = args_parser.parse_args()
  run(args.program)
