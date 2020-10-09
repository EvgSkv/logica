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

"""A suite of tests for import functionality."""

from common import logica_test


def RunTest(name, src, golden, predicate, user_flags=None):
  """Run one test from this folder with TestManager."""
  logica_test.TestManager.RunTest(
      name,
      src="integration_tests/import_tests/" + src,
      golden="integration_tests/import_tests/" + golden,
      predicate=predicate,
      user_flags=user_flags)


def RunAll():
  """Run all the tests."""
  RunTest(
      name="canada_psql_test",
      src="canada_psql_test.l",
      golden="canada_psql_Consume.txt",
      predicate="TestConsume",
  )

  RunTest(
      name="functor_test",
      src="functor_test.l",
      golden="functor_test.txt",
      predicate="Test",
  )

  RunTest(
      name="canada_import_fraction_test",
      src="canada_test.l",
      golden="canada_ImportFraction.txt",
      predicate="TestImportFraction",
  )

  RunTest(
      name="canada_consume_test",
      src="canada_test.l",
      golden="canada_Consume.txt",
      predicate="TestConsume",
  )

  RunTest(
      name="canada_imported_engineer_test",
      src="canada_test.l",
      golden="canada_ImportedEngineer.txt",
      predicate="TestImportedEngineer",
  )

