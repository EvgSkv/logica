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
"""Utilities for YotaQL tests."""

import os
import subprocess
import json

if '.' not in __package__:
  from common import color
  from common import logica_lib
  from tools import run_in_terminal
  from type_inference.research import infer
  from parser_py import parse
else:
  from ..common import color
  from ..common import logica_lib
  from ..tools import run_in_terminal
  from ..type_inference.research import infer
  from ..parser_py import parse


class TestManager(object):
  """Global test managing class."""
  GOLDEN_RUN = False
  ANNOUNCE_TESTS = False
  RUN_ONLY = []

  @classmethod
  def SetGoldenRun(cls, value):
    cls.GOLDEN_RUN = value

  @classmethod
  def SetAnnounceTests(cls, value):
    cls.ANNOUNCE_TESTS = value

  @classmethod
  def SetRunOnlyTests(cls, value):
    cls.RUN_ONLY = value

  @classmethod
  def RunTest(cls, name, src, predicate, golden, user_flags,
              import_root=None, use_concertina=False,
              duckify_psql=False):
    if cls.RUN_ONLY and name not in cls.RUN_ONLY:
      return
    RunTest(name, src, predicate, golden, user_flags,
            cls.GOLDEN_RUN, cls.ANNOUNCE_TESTS,
            import_root, use_concertina, duckify_psql)

  @classmethod
  def RunTypesTest(cls, name, src=None, golden=None):
    if cls.RUN_ONLY and name not in cls.RUN_ONLY:
      return
    RunTypesTest(name, src, golden,
                 overwrite=cls.GOLDEN_RUN)


def RunTypesTest(name, src=None, golden=None,
                 overwrite=False):
  src = src or (name + '.l')
  golden = golden or (name + '.txt')

  test_result = '{warning}RUNNING{end}'
  print(color.Format('% 50s   %s' % (name, test_result)))

  program_text = open(src).read()
  try:
    parsed_rules = parse.ParseFile(program_text)['rule']
  except parse.ParsingException as parsing_exception:
    parsing_exception.ShowMessage()
    sys.exit(1)

  typing_engine = infer.TypesInferenceEngine(parsed_rules, dialect='psql')
  typing_engine.InferTypes()
  result = json.dumps(parsed_rules, sort_keys=True, indent=' ')

  if overwrite:
    with open(golden, 'w') as w:
      w.write(result)
  golden_result = open(golden).read()

  if result == golden_result:
    test_result = '{ok}PASSED{end}'
  else:
    p = subprocess.Popen(['diff', '-', golden], stdin=subprocess.PIPE)
    p.communicate(result.encode())
    test_result = '{error}FAILED{end}'

  print('\033[F\033[K' + color.Format('% 50s   %s' % (name, test_result)))


def RunTest(name, src, predicate, golden,
            user_flags=None,
            overwrite=False, announce=False,
            import_root=None, use_concertina=False,
            duckify_psql=False):
  """Run one test."""
  if announce:
    print('Running test:', name)
  test_result = '{warning}RUNNING{end}'
  print(color.Format('% 50s   %s' % (name, test_result)))
  if duckify_psql:
    duck_src = '/tmp/%s.l' % name
    with open(duck_src, 'w') as duck_source:
      duck_source.write(open(src).read().replace('"psql"', '"duckdb"'))
    src = duck_src
  if use_concertina:
    result = run_in_terminal.Run(src, predicate, display_mode='silent')
  else:
    result = logica_lib.RunPredicate(src, predicate,
                                     user_flags=user_flags,
                                     import_root=import_root)
  # Hacky way to remove query that BQ prints.
  if '+---' in result[200:]:
    result = result[result.index('+---'):]

  if overwrite:
    with open(golden, 'w') as w:
      w.write(result)
  if not os.path.isfile(golden):
    golden_result = 'This file does not exist. (<_<)'
  else:
    golden_result = open(golden).read()

  if result == golden_result:
    test_result = '{ok}PASSED{end}'
  else:
    # print('\n' * 3)
    # print(golden_result)
    # print(result)
    # print('\n' * 3)
    p = subprocess.Popen(['diff', '--strip-trailing-cr', '-', golden], stdin=subprocess.PIPE)
    p.communicate(result.encode())
    if golden_result == 'This file does not exist. (<_<)':
      print('\x1B[3mGolden file is missing.\x1B[0m\n')

    test_result = '{error}FAILED{end}'

  print('\033[F\033[K' + color.Format('% 50s   %s' % (name, test_result)))


def PrintHeader():
  """Print header for all tests."""
  print(color.Format(
      '% 64s   %s' % ('{warning}TEST{end}', '{warning}RESULT{end}')))
  print(color.Format(
      '% 64s   %s' % ('{warning}----{end}', '{warning}------{end}')))

