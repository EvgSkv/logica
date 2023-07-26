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

# Example of running Logica on PostgreSQL from Python.
# Additional libraries to be installed if using logica as a library:
# `pip install psycopg2`
# Assuming a PostgreSQL connection shown as a  terminal command below:
#  PGPASSWORD=somepassword psql -d postgres -U postgres -h localhost
# To run: python3 call_postgres.py

from logica.common import logica_lib
from sqlalchemy import create_engine
print('Calculating primes.')
engine = create_engine('postgresql+psycopg2://postgres:somepassword@localhost', pool_recycle=3600)
connection = engine.connect()
primes = logica_lib.RunPredicateToPandas(
    '../scripts/primes_postgresql.l',
    'Prime',
    connection=connection)
print('Found %d primes.' % len(primes))
print('Primes:', list(primes['prime']))



