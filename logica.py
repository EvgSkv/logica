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

# We are doing this 'if' to allow usage of the code as package and as a
# script.
if __name__ == '__main__' and not __package__:
  from common import color
  from common import sqlite3_logica
  from compiler import functors
  from compiler import rule_translate
  from compiler import universe
  from parser_py import parse
  from type_inference.research import infer
  from type_inference import type_retrieval_service_discovery
else:
  from .common import color
  from .common import sqlite3_logica
  from .compiler import functors
  from .compiler import rule_translate
  from .compiler import universe
  from .parser_py import parse
  from .type_inference.research import infer
  from .type_inference import type_retrieval_service_discovery


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


def GetImportRoot():
  """Parses LOGICAPATH environment variable."""
  import_root_env = os.environ.get('LOGICAPATH')
  if not import_root_env:
    return None
  roots = import_root_env.split(':')
  if len(roots) > 1:
    return roots
  else:
    return import_root_env


def GetTrinoParameters(a):
  boolean_parameters = [
    "debug", "disable-compression", "ignore-errors",
    "insecure", "krb5-disable-remote-service-hostname-canonicalization",
    "password", "progress"]
  parameters = [
    "access-token", "catalog", "client-info", "client-request-timeout",
    "client-tags", "execute", "external-authentication",
    "extra-credential", "http-proxy", "keystore-password",
    "keystore-path", "keystore-type", "krb5-config-path",
    "krb5-credential-cache-path", "krb5-keytab-path",
    "krb5-principal", "krb5-remote-service-name",
    "krb5-service-principal-pattern", "log-levels-file",
    "resource-estimate", "schema", "server", "session",
    "session-user", "socks-proxy", "source", "timezone", "trace-token",
    "truststore-password", "truststore-path", "truststore-type", "user"]
  boolean_params = ["--%s" % p for p in boolean_parameters
    if (p in a and type(a.get(p)) == bool and a.get(p))]
  params = ["--%s=%s" % (p, a.get(p)) for p in parameters if p in a]
  if "catalog" not in a:
    params.append("--catalog=memory")
  return boolean_params + params


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

  if len(argv) == 3 and argv[2] in ['parse', 'infer_types', 'show_signatures']:
    pass  # compile needs just 2 actual arguments.
  else:
    if len(argv) < 4:
      print('Not enough arguments. Run \'logica help\' for help.',
            file=sys.stderr)
      return 1
    predicates = argv[3]

  if argv[1] == '-':
    filename = '/dev/stdin'
  else:
    filename = argv[1]

  command = argv[2]

  commands = ['parse', 'print', 'run', 'run_to_csv', 'run_in_terminal',
              'infer_types', 'show_signatures', 'build_schema']

  if command not in commands:
    print(color.Format('Unknown command {warning}{command}{end}. '
                       'Available commands: {commands}.',
                       dict(command=command, commands=', '.join(commands))))
    return 1
  if not os.path.exists(filename):
    print('File not found: %s' % filename, file=sys.stderr)
    return 1

  # This has to be before reading program.
  if command == 'run_in_terminal':
    if __name__ == '__main__' and not __package__:
      from tools import run_in_terminal
    else:
      from .tools import run_in_terminal
    artistic_table = run_in_terminal.Run(filename, predicates)
    print(artistic_table)
    return

  program_text = open(filename).read()

  try:
    parsed_rules = parse.ParseFile(program_text,
                                   import_root=GetImportRoot())['rule']
  except parse.ParsingException as parsing_exception:
    parsing_exception.ShowMessage()
    sys.exit(1)

  if command == 'parse':
    # Minimal indentation for better readability of deep objects.
    print(json.dumps(parsed_rules, sort_keys=True, indent=' '))
    return 0

  if command == 'infer_types':
    # This disallows getting types of program with type errors.
    # logic_program = universe.LogicaProgram(parsed_rules)
    # TODO: Find a way to get engine from program. But it should not matter
    # for inference. It only patters for compiling.
    typing_engine = infer.TypesInferenceEngine(parsed_rules, "psql")
    typing_engine.InferTypes()
    # print(parsed_rules)
    print(json.dumps(parsed_rules, sort_keys=True, indent=' '))
    return 0

  if command == 'show_signatures':
    try:
      logic_program = universe.LogicaProgram(parsed_rules)
      if not logic_program.typing_engine:
        logic_program.RunTypechecker()
    except infer.TypeErrorCaughtException as type_error_exception:
      print(logic_program.typing_engine.ShowPredicateTypes())
      type_error_exception.ShowMessage()
      return 1
    print(logic_program.typing_engine.ShowPredicateTypes())
    return 0

  predicates_list = predicates.split(',')

  user_flags = ReadUserFlags(parsed_rules, argv[4:])

  if command == 'build_schema':
    logic_program = universe.LogicaProgram(parsed_rules, user_flags=user_flags)
    engine = logic_program.annotations.Engine()
    type_retrieval_service = type_retrieval_service_discovery\
      .get_type_retrieval_service(engine, parsed_rules, predicates_list)
    type_retrieval_service.RetrieveTypes(filename)
    return 0

  for predicate in predicates_list:
    try:
      logic_program = universe.LogicaProgram(
          parsed_rules, user_flags=user_flags)
      formatted_sql = logic_program.FormattedPredicateSql(predicate)
      preamble = logic_program.execution.preamble
      defines_and_exports = logic_program.execution.defines_and_exports
      main_predicate_sql = logic_program.execution.main_predicate_sql
    except rule_translate.RuleCompileException as rule_compilation_exception:
      rule_compilation_exception.ShowMessage()
      sys.exit(1)
    except functors.FunctorError as functor_exception:
      functor_exception.ShowMessage()
      sys.exit(1)
    except infer.TypeErrorCaughtException as type_error_exception:
      type_error_exception.ShowMessage()
      sys.exit(1)
    except parse.ParsingException as parsing_exception:
      parsing_exception.ShowMessage()
      sys.exit(1)

    if command == 'print':
      print(formatted_sql)

    engine = logic_program.annotations.Engine()

    if command == 'run' or command == 'run_to_csv':
      # We should split and move this logic to dialects.
      if engine == 'bigquery':
        output_format = 'csv' if command == 'run_to_csv' else 'pretty'
        p = subprocess.Popen(['bq', 'query',
                              '--use_legacy_sql=false',
                              '--format=%s' % output_format],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        o, _ = p.communicate(formatted_sql.encode())
      elif engine == 'sqlite':
        # TODO: Make multi-statement scripts work.
        format = ('artistictable' if command == 'run' else 'csv')
        statements_to_execute = (
          [preamble] + defines_and_exports + [main_predicate_sql])
        o = sqlite3_logica.RunSqlScript(statements_to_execute,
                                        format).encode()
      elif engine == 'duckdb':
        import duckdb
        cur = duckdb.sql(formatted_sql)
        o = sqlite3_logica.ArtisticTable(cur.columns,
                                         cur.fetchall()).encode()
      elif engine == 'psql':
        connection_str = os.environ.get('LOGICA_PSQL_CONNECTION')
        if connection_str:
          connection_str = os.environ.get('LOGICA_PSQL_CONNECTION')
          import psycopg2
          from common import psql_logica
          connection = psycopg2.connect(connection_str)
          cursor = psql_logica.PostgresExecute(formatted_sql, connection)
          rows = [list(map(psql_logica.DigestPsqlType, row))
              
                  for row in cursor.fetchall()]
          o = sqlite3_logica.ArtisticTable([d[0] for d in cursor.description],
                                           rows).encode()
        else:
          p = subprocess.Popen(['psql', '--quiet'] +
                              (['--csv'] if command == 'run_to_csv' else []),
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE)
          commands = []
          o, _ = p.communicate(
              '\n'.join(commands + [formatted_sql]).encode())
      elif engine == 'trino':
        a = logic_program.annotations.annotations['@Engine']['trino']
        params = GetTrinoParameters(a)
        p = subprocess.Popen(['trino'] + params +
                             (['--output-format=CSV_HEADER_UNQUOTED']
                              if command == 'run_to_csv' else
                              ['--output-format=ALIGNED']),
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        o, _ = p.communicate(formatted_sql.encode())
      elif engine == 'presto':
        a = logic_program.annotations.annotations['@Engine']['presto']
        catalog = a.get('catalog', 'memory')
        server = a.get('server', 'localhost:8080')
        p = subprocess.Popen(['presto',
                              '--catalog=%s' % catalog,
                              '--server=%s' % server,
                              '--file=/dev/stdin'] +
                             (['--output-format=CSV_HEADER_UNQUOTED']
                              if command == 'run_to_csv' else
                              ['--output-format=ALIGNED']),
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        o, _ = p.communicate(formatted_sql.encode())
      else:
        assert False, 'Unknown engine: %s' % engine
      print(o.decode())


def run_main():
  """Run main function with system arguments."""
  main(sys.argv)


if __name__ == '__main__':
  main(sys.argv)
