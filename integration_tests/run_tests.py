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


def RunTest(name, src=None, golden=None, predicate=None,
            user_flags=None):
  """Run one test from this folder with TestManager."""
  src = src or (name + ".l")
  golden = golden or (name + ".txt")
  predicate = predicate or "Test"
  logica_test.TestManager.RunTest(
      name,
      src="integration_tests/" + src,
      golden="integration_tests/" + golden,
      predicate=predicate,
      user_flags=user_flags)


def RunAll():
  """Running all tests."""
  # Uncomment to test writing tables.
  # RunTest("ground_test")
  # RunTest("ground_psql_test")
  RunTest("psql_test")
  RunTest("sqlite_subquery_test")

  RunTest("sqlite_test")

  RunTest(
      name="quote_escape_test",
      src="quote_escape_test.l",
      golden="quote_escape_test.txt",
      predicate="Q",
      user_flags={'name': 'Dwayne "Rock" Johnson'}
  )

  RunTest("array_test")
  RunTest("udf_test")
  RunTest("with_test")

  RunTest(
      name="factorial_test",
      src="factorial_test.l",
      golden="factorial_test.txt",
      predicate="Test"
  )

  RunTest(
      name="sql_expr_test",
      src="sql_expr_test.l",
      golden="sql_expr_test.txt",
      predicate="Test",
  )

  RunTest(
      name="unnest_order_test",
      src="unnest_order_test.l",
      golden="unnest_order_test.txt",
      predicate="Test",
  )

  RunTest(
      name="nested_combines_test",
      src="nested_combines_test.l",
      golden="nested_combines_test.txt",
      predicate="Test",
  )

  RunTest(
      name="analytic_test",
      src="analytic_test.l",
      golden="analytic_test.txt",
      predicate="ReadableTest",
  )

  RunTest(
      name="simple_functors_test",
      src="simple_functors_test.l",
      golden="simple_functors_test.txt",
      predicate="Test",
  )

  RunTest(
      name="composite_functor_test",
      src="composite_functor_test.l",
      golden="composite_functor_test.txt",
      predicate="AnonymizedTrafficUS",
  )

  RunTest(
      name="long_functor_test",
      src="long_functor_test.l",
      golden="long_functor_test.txt",
      predicate="F7",
  )

  RunTest(
      name="nontrivial_restof_test",
      src="nontrivial_restof_test.l",
      golden="nontrivial_restof_test.txt",
      predicate="Test",
  )

  RunTest(
      name="cast_test",
      src="cast_test.l",
      golden="cast_test.txt",
      predicate="T",
  )

  RunTest(
      name="disjunction_test",
      src="disjunction_test.l",
      golden="disjunction_test.txt",
      predicate="Answer",
  )

  RunTest(
      name="arg_min_max_test",
      src="arg_min_max_test.l",
      golden="arg_min_max_test.txt",
      predicate="Test",
  )

  RunTest(
      name="operation_order_test",
      src="operation_order_test.l",
      golden="operation_order_test.txt",
      predicate="Test",
  )

  RunTest(
      name="no_from_test",
      src="no_from_test.l",
      golden="no_from_test.txt",
      predicate="Test",
  )

  RunTest(
      name="if_then_test",
      src="if_then.l",
      golden="if_then_QualifiedSummary.txt",
      predicate="QualifiedSummary",
  )

  RunTest(
      name="modification_inside_test",
      src="modification_inside.l",
      golden="modification_inside.txt",
      predicate="BetterCountry",
  )

  RunTest(
      name="outer_join_test",
      src="outer_join.l",
      golden="outer_join_test.txt",
      predicate="PersonPhonesAndEmails",
  )

  RunTest(
      name="outer_join_some_value_test",
      src="outer_join_some_value.l",
      golden="outer_join_verbose_test.txt",
      predicate="PersonPhoneAndEmail",
  )

  RunTest(
      name="outer_join_disjunction_test",
      src="outer_join_disjunction.l",
      golden="outer_join_verbose_test.txt",
      predicate="PersonPhoneAndEmail",
  )

  RunTest(
      name="outer_join_combine_test",
      src="outer_join_combine.l",
      golden="outer_join_verbose_test.txt",
      predicate="PersonPhoneAndEmail",
  )

  RunTest(
      name="outer_join_verbose_test",
      src="outer_join_verbose.l",
      golden="outer_join_verbose_test.txt",
      predicate="PersonPhoneAndEmail",
  )

  RunTest(
      name="multi_body_aggregation_test",
      src="multi_body_aggregation.l",
      golden="multi_body_aggregation_test.txt",
      predicate="TestOutput",
  )

  RunTest(
      name="bulk_functions_test",
      src="bulk_functions.l",
      golden="bulk_functions_test.txt",
      predicate="Test",
  )

  RunTest(
      name="define_aggregation_test",
      src="define_aggregation.l",
      golden="define_aggregation_test.txt",
      predicate="SampledPeople",
  )

  RunTest(
      name="unary_test",
      src="unary_test.l",
      golden="unary_test.txt",
      predicate="Test",
  )

  RunTest(
      name="sql_string_table_test",
      src="sql_string_table_test.l",
      golden="sql_string_table_test.txt",
      predicate="Test",
  )
