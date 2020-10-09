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

from compiler import functors
from compiler import rule_translate
from compiler import universe
from parser_py import parse


def ParseOrExit(filename):
  """Parse a Logica program."""
  with open(filename) as f:
    program_text = f.read()

  try:
    parsed_rules = parse.ParseFile(program_text)['rule']
  except parse.ParsingException as parsing_exception:
    parsing_exception.ShowMessage()
    sys.exit(1)

  return parsed_rules


def GetProgramOrExit(filename, user_flags=None):
  """Get program object from a file."""
  parsed_rules = ParseOrExit(filename)
  try:
    p = universe.LogicaProgram(parsed_rules, user_flags=user_flags)
  except rule_translate.RuleCompileException as rule_compilation_exception:
    rule_compilation_exception.ShowMessage()
    sys.exit(1)
  except functors.FunctorError as functor_exception:
    functor_exception.ShowMessage()
    sys.exit(1)
  return p


def RunQuery(sql, output_format='pretty', engine='bigquery'):
  """Run a SQL query on BigQuery."""
  if engine == 'bigquery':
    p = subprocess.Popen(['bq', 'query',
                          '--use_legacy_sql=false',
                          '--format=%s' % output_format],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE)
  elif engine == 'sqlite':
    p = subprocess.Popen(['sqlite3'],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE)
  elif engine == 'psql':
    p = subprocess.Popen(['psql', '--quiet'],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE)
  else:
    assert False, 'Unknown engine: %s' % engine
  o, _ = p.communicate(sql.encode())
  return o.decode()


def RunPredicate(filename, predicate,
                 output_format='pretty', user_flags=None):
  """Run a predicate on BigQuery."""
  p = GetProgramOrExit(filename, user_flags=user_flags)
  sql = p.FormattedPredicateSql(predicate)
  return RunQuery(sql, output_format, engine=p.annotations.Engine())
