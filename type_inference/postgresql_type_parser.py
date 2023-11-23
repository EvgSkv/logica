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

POSTGRES_TYPE_TO_LOGICA_TYPE = {
  'boolean': 'Bool',
  'bool': 'Bool',
  'bigint': 'Num',
  'int8': 'Num',
  'bigserial': 'Num',
  'serial8': 'Num',
  'double precision': 'Num',
  'float8': 'Num',
  'integer': 'Num',
  'int': 'Num',
  'int4': 'Num',
  'money': 'Num',
  'real': 'Num',
  'float4': 'Num',
  'smallint': 'Num',
  'int2': 'Num',
  'smallserial': 'Num',
  'serial2': 'Num',
  'serial': 'Num',
  'serial4': 'Num',
  'varbit': 'Str',
  'box': 'Str',
  'bytea': 'Str',
  'cidr': 'Str',
  'circle': 'Str',
  'date': 'Str',
  'inet': 'Str',
  'json': 'Str',
  'jsonb': 'Str',
  'line': 'Str',
  'lseg': 'Str',
  'macaddr': 'Str',
  'path': 'Str',
  'pg_lsn': 'Str',
  'point': 'Str',
  'polygon': 'Str',
  'text': 'Str',
  'timetz': 'Str',
  'timestamptz': 'Str',
  'tsquery': 'Str',
  'tsvector': 'Str',
  'txid_snapshot': 'Str',
  'uuid': 'Str',
  'xml': 'Str'
}


def PostgresTypeToLogicaType(pg_type: str) -> str | None:
  """Parses psql atomic type into logica type, drops parameter if needed."""
  def TryParseParametrizedPostgresTypeToLogicaType(pg_type: str) -> str | None:
    if pg_type.startswith('numeric'):
      return 'Num'
    elif pg_type.startswith('decimal'):
      return 'Num'
    elif pg_type.startswith('bit'):
      return 'Str'
    elif pg_type.startswith('char'):
      return 'Str'
    elif pg_type.startswith('varchar'):
      return 'Str'
    elif pg_type.startswith('interval'):
      return 'Str'
    elif pg_type.startswith('time'):
      return 'Str'
    return None

  type_in_lowercase = pg_type.lower()

  if type_in_lowercase in POSTGRES_TYPE_TO_LOGICA_TYPE:
    return POSTGRES_TYPE_TO_LOGICA_TYPE[type_in_lowercase]
  else:
    return TryParseParametrizedPostgresTypeToLogicaType(type_in_lowercase)
