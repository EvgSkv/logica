#!/usr/bin/python
#
# Copyright 2023 Google LLC
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

# Playground to evaluate multiset propositions.

import os
import readline  # Dark magic.

if not __package__ or '.' not in __package__:
  from parser_py import parse
  from common import sqlite3_logica
  from common import logica_lib
  from compiler import rule_translate
else:
  from ..parser_py import parse
  from ..common import sqlite3_logica
  from ..common import logica_lib
  from ..compiler import rule_translate


def AssignedVariables(proposition):
  result = None
  dnf = parse.DisjunctiveNormalForm.PropositionToDNF(proposition)
  for conjunct in dnf:
    vars = rule_translate.AllMentionedVariables(conjunct)
    if result is None:
      result = set(vars)
    else:
      result &= set(vars)
  return list(sorted(result))


def ParsePropositionOrExit(c):
  try:
    c = parse.Strip(parse.HeritageAwareString(c))
    return parse.ParseProposition(c)
  except parse.ParsingException as parsing_exception:
    parsing_exception.ShowMessage()
    return 'this is bad'


def GiveMeABreak(x):
  return ('select \'yup\' as error', 'duckdb')

def Repl(context):
  print('Welcome to Logica propositional playground.')
  print('Enter proposition to compute table for, for example you can enter: x = 1')
  print('Empty propisition to exit.')
  # Load history before existing code runs
  history_file = os.path.expanduser("~/.logica_history")

  # Check if file exists before reading
  if os.path.exists(history_file):
    readline.read_history_file(history_file)

  logica_lib.HandleException = GiveMeABreak
  while True:
    c = input('> ')
    if not c:
      print('Bye!')
      readline.write_history_file(history_file)
      os.chmod(history_file, 0o660)
      return
    t = ParsePropositionOrExit(c)
    if t == 'this is bad':
      continue
    v = AssignedVariables(t)
    order_clause = (
        '@OrderBy(Q, %s);' %  ','.join(['"%s"' % x for x in v]) if v else '')
    df = logica_lib.RunPredicateFromString(
        context +
        order_clause +
        'Q(%s) :- %s' % (
        ','.join([x + ':' + x for x in v]),
        c
        ),
        'Q')
    print(sqlite3_logica.DataframeAsArtisticTable(df))