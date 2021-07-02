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

# Lint as: python3
"""Common utilities for Logica predicate compilation and execution."""

import subprocess
import sys

if '.' not in __package__:
  from common import sqlite3_logica
  from compiler import functors
  from compiler import rule_translate
  from compiler import universe
  from parser_py import parse
else:
  from ..common import sqlite3_logica
  from ..compiler import functors
  from ..compiler import rule_translate
  from ..compiler import universe
  from ..parser_py import parse


def ParseOrExit(filename, import_root=None):
  """Parse a Logica program."""
  with open(filename) as f:
    program_text = f.read()

  try:
    parsed_rules = parse.ParseFile(program_text,
                                   import_root=import_root)['rule']
  except parse.ParsingException as parsing_exception:
    parsing_exception.ShowMessage()
    sys.exit(1)

  return parsed_rules


def GetProgramOrExit(filename, user_flags=None, import_root=None):
  """Get program object from a file."""
  parsed_rules = ParseOrExit(filename, import_root=import_root)
  try:
    p = universe.LogicaProgram(parsed_rules, user_flags=user_flags)
  except rule_translate.RuleCompileException as rule_compilation_exception:
    rule_compilation_exception.ShowMessage()
    sys.exit(1)
  except functors.FunctorError as functor_exception:
    functor_exception.ShowMessage()
    sys.exit(1)
  return p


def RunQuery(sql,
             settings=None,
             output_format='pretty', engine='bigquery'):
  """Run a SQL query on BigQuery."""
  settings = settings or {}
  if engine == 'bigquery':
    p = subprocess.Popen(['bq', 'query',
                          '--use_legacy_sql=false',
                          '--format=%s' % output_format],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE)
  elif engine == 'sqlite':
    # TODO: Make multi-statement scripts work.
    return sqlite3_logica.RunSQL(sql)
  elif engine == 'psql':
    p = subprocess.Popen(['psql', '--quiet'],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE)
  elif engine == 'trino':
    catalog = settings.get('catalog', 'memory')
    server = settings.get('server', 'http://localhost:8080')
    p = subprocess.Popen(['trino',
                          '--catalog=%s' % catalog,
                          '--server=%s' % server] +
                          ['--output-format=ALIGNED'],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE)
  elif engine == 'presto':
    catalog = settings.get('catalog', 'memory')
    server = settings.get('server', 'http://localhost:8080')
    p = subprocess.Popen(['presto',
                          '--catalog=%s' % catalog,
                          '--server=%s' % server,
                          '--file=/dev/stdin'] +
                          ['--output-format=ALIGNED'],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE)
  else:
    assert False, 'Unknown engine: %s' % engine
  o, _ = p.communicate(sql.encode())
  return o.decode()


def RunPredicate(filename, predicate,
                 output_format='pretty', user_flags=None,
                 import_root=None):
  """Run a predicate on BigQuery."""
  p = GetProgramOrExit(filename, user_flags=user_flags,
                       import_root=import_root)
  sql = p.FormattedPredicateSql(predicate)
  engine = p.annotations.Engine()
  if ('@Engine' in p.annotations.annotations and
      engine in p.annotations.annotations['@Engine']):
    settings = p.annotations.annotations['@Engine'][engine]
  else:
    settings = {}
  return RunQuery(sql, settings,
                  output_format, engine=engine)
