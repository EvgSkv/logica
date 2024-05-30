#!/usr/bin/python
#
# Copyright 2023 Logica Authors
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

POSTGRES_NUM_TYPE_PREFIXES = [
  'numeric',
  'decimal',
  'int',
  'serial',
  'bigint',
  'bigserial',
  'double precision',
  'float',
  'money',
  'real',
  'smallint',
  'smallserial',
]


def PostgresTypeToLogicaType(pg_type: str):
  """Parses psql atomic type into logica type, drops parameter if needed."""
  type_in_lowercase = pg_type.lower()

  if type_in_lowercase.startswith('bool'):
    return 'Bool'

  for num_prefix in POSTGRES_NUM_TYPE_PREFIXES:
    if type_in_lowercase.startswith(num_prefix):
      return 'Num'

  return 'Str'
