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

# Example of running Logica on SQLite from Python.
# To run: python3 call_sqlite.py

from logica.common import logica_lib
print('Calculating primes.')
primes = logica_lib.RunPredicateToPandas(
    '../scripts/primes_sqlite.l',
    'Prime')
print('Found %d primes.' % len(primes))
print('Primes:', list(primes['prime']))
