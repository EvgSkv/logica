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

"""A suite of tests for type inference."""

from common import logica_test

def RunTypesTest(name, src=None, golden=None):
  src = src or (
    'type_inference/research/integration_tests/' + name + '.l')
  golden = golden or (
    'type_inference/research/integration_tests/' + name + '.txt')
  logica_test.TestManager.RunTypesTest(name, src, golden)

def RunAll():
  RunTypesTest('typing_palindrome_puzzle_test')
  RunTypesTest('typing_kitchensync_test')
  RunTypesTest('typing_basic_test')
  RunTypesTest('typing_aggregation_test')
  RunTypesTest('typing_lists_test')
  RunTypesTest('typing_nested_test')
  RunTypesTest('typing_combines_test')
  RunTypesTest('typing_combine2_test')

if __name__ == '__main__':
  RunAll()