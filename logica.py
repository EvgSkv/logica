#!/usr/bin/python
#
# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Logica command-line tool.

Example usage:

python3 logica.py - run Grandparent <<<'
Parent(parent: "Shmi Skywalker", child: "Anakin Skywalker");
Parent(parent: "Anakin Skywalker", child: "Luke Skywalker");
Grandparent(grandparent:, grandchild:) :-
  Parent(parent: grandparent, child: x),
  Parent(parent: x, child: grandchild);
'

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import getopt
import json
import os
import subprocess
import sys


from common import color
from compiler import functors
from compiler import rule_translate
from compiler import universe
from parser_py import parse


def ReadUserFlags(rules, argv):
  """Reading logic program flags provided by the user."""
  def Error(msg):
    print(color.Format('[ {error}Error{end} ] {msg}', {'msg': msg}))
    sys.exit(1)

  annotations = universe.Annotations.ExtractAnnotations(
      rules, restrict_to=['@DefineFlag'])
  defined_flags = annotations['@DefineFlag'].keys()
  try:
    p = getopt.getopt(argv, '', ['%s=' % f for f in defined_flags])
  except getopt.GetoptError as e:
    Error(str(e))

  if p[1]:
    Error('Undefined command arguments: %s' % p[1])

    sys.exit(1)
  user_flags = {k[2:]: v for k, v in p[0]}
  return user_flags


def main(argv):
  if len(argv) <= 1 or argv[1] == 'help':
    print('Usage:')
    print('  logica <l file> <command> <predicate name> [flags]')
    print('  Commands are:')
    print('    print: prints the StandardSQL query for the predicate.')
    print('    run: runs the StandardSQL query on BigQuery with pretty output.')
    print('    run_to_csv: runs the query on BigQuery with csv output.')

    print('')
    print('')
    print('Example:')
    print('  python3 logica.py - run GoodIdea <<<\' '
          'GoodIdea(snack: "carrots")\'')
    return 1

  if len(argv) == 3 and argv[2] == 'parse':
    pass  # compile needs just 2 actual arguments.
  else:
    if len(argv) < 4:
      print('Not enought arguments. Run \'logica help\' for help.',
            file=sys.stderr)
      return 1

  if argv[1] == '-':
    filename = '/dev/stdin'
  else:
    filename = argv[1]

  command = argv[2]

  commands = ['parse', 'print', 'run', 'run_to_csv']

  if command not in commands:
    print(color.Format('Unknown command {warning}{command}{end}. '
                       'Available commands: {commands}.',
                       dict(command=command, commands=', '.join(commands))))
    return 1
  if not os.path.exists(filename):
    print('File not found: %s' % filename, file=sys.stderr)
    return 1
  program_text = open(filename).read()

  try:
    parsed_rules = parse.ParseFile(program_text)['rule']
  except parse.ParsingException as parsing_exception:
    parsing_exception.ShowMessage()
    sys.exit(1)

  if command == 'parse':
    # No indentation to avoid file size inflation.
    print(json.dumps(parsed_rules, sort_keys=True, indent=''))
    return 0

  predicates = argv[3]

  user_flags = ReadUserFlags(parsed_rules, argv[4:])

  predicates_list = predicates.split(',')
  for predicate in predicates_list:
    try:
      p = universe.LogicaProgram(parsed_rules, user_flags=user_flags)
      formatted_sql = p.FormattedPredicateSql(predicate)
    except rule_translate.RuleCompileException as rule_compilation_exception:
      rule_compilation_exception.ShowMessage()
      sys.exit(1)
    except functors.FunctorError as functor_exception:
      functor_exception.ShowMessage()
      sys.exit(1)

    if command == 'print':
      print(formatted_sql)

    engine = p.annotations.Engine()

    if command == 'run' or command == 'run_to_csv':
      if engine == 'bigquery':
        output_format = 'csv' if command == 'run_to_csv' else 'pretty'
        p = subprocess.Popen(['bq', 'query',
                              '--use_legacy_sql=false',
                              '--format=%s' % output_format],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        o, _ = p.communicate(formatted_sql.encode())
      elif engine == 'sqlite':
        p = subprocess.Popen(['sqlite3'],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        commands = []
        if command == 'run_to_csv':
          commands.append('.mode csv')
        o, _ = p.communicate(
            '\n'.join(commands + [formatted_sql]).encode())
      elif engine == 'psql':
        p = subprocess.Popen(['psql', '--quiet'] +
                             (['--csv'] if command == 'run_to_csv' else []),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        commands = []
        o, _ = p.communicate(
            '\n'.join(commands + [formatted_sql]).encode())
      else:
        assert False, 'Unknown engine: %s' % engine
      print(o.decode())

if __name__ == '__main__':
  main(sys.argv)
