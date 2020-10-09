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
"""Running all integration tests."""

import sys
from common import logica_test
from integration_tests import run_tests as integration_tests
from integration_tests.import_tests import run_tests as import_tests


if 'golden_run' in sys.argv:
  logica_test.TestManager.SetGoldenRun(True)

if 'announce_tests' in sys.argv:
  logica_test.TestManager.SetAnnounceTests(True)

for a in sys.argv:
  if a.startswith('test_only='):
    logica_test.TestManager.SetRunOnlyTests(a.split('=')[1].split(','))

logica_test.PrintHeader()

integration_tests.RunAll()
import_tests.RunAll()
