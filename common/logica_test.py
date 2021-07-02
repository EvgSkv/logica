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

import subprocess

if '.' not in __package__:
  from common import color
  from common import logica_lib
else:
  from ..common import color
  from ..common import logica_lib


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
              import_root=None):
    if cls.RUN_ONLY and name not in cls.RUN_ONLY:
      return
    RunTest(name, src, predicate, golden, user_flags,
            cls.GOLDEN_RUN, cls.ANNOUNCE_TESTS,
            import_root)


def RunTest(name, src, predicate, golden,
            user_flags=None,
            overwrite=False, announce=False,
            import_root=None):
  """Run one test."""
  if announce:
    print('Running test:', name)
  test_result = '{warning}RUNNING{end}'
  print(color.Format('% 50s   %s' % (name, test_result)))

  result = logica_lib.RunPredicate(src, predicate,
                                   user_flags=user_flags,
                                   import_root=import_root)
  # Hacky way to remove query that BQ prints.
  if '+---' in result[200:]:
    result = result[result.index('+---'):]

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


def PrintHeader():
  """Print header for all tests."""
  print(color.Format(
      '% 64s   %s' % ('{warning}TEST{end}', '{warning}RESULT{end}')))
  print(color.Format(
      '% 64s   %s' % ('{warning}----{end}', '{warning}------{end}')))

