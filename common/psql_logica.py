#!/usr/bin/python
#
# Copyright 2023 Google LLC
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

import getpass
import json
import os
import re
from decimal import Decimal

if '.' not in __package__:
  from type_inference.research import infer
else:
  from ..type_inference.research import infer


def PostgresExecute(sql, connection):
  import psycopg2
  import psycopg2.extras
  cursor = connection.cursor()
  try:
    cursor.execute(sql)
    # Make connection aware of the used types.
    types = re.findall(r'-- Logica type: (\w*)', sql)
    for t in types:
      if t != 'logicarecord893574736':  # Empty record.
        psycopg2.extras.register_composite(t, cursor, globally=True)
  except psycopg2.errors.UndefinedTable  as e:
    raise infer.TypeErrorCaughtException(
      infer.ContextualizedError.BuildNiceMessage(
        'Running SQL.', 'Undefined table used: ' + str(e)))
  except psycopg2.Error as e:
    connection.rollback()
    raise e
  return cursor


def DigestPsqlType(x):
  if isinstance(x, tuple):
    return PsqlTypeAsDictionary(x)
  if isinstance(x, list) and len(x) > 0:
    return PsqlTypeAsList(x)
  if isinstance(x, Decimal):
    if x.as_integer_ratio()[1] == 1:
      return int(x)
    else:
      return float(x)
  return x


def PsqlTypeAsDictionary(record):
  result = {}
  for f in record._asdict():
    a = getattr(record, f)
    result[f] = DigestPsqlType(a)
  return result


def PsqlTypeAsList(a):
  return list(map(DigestPsqlType, a))

REMEMBERED_CONNECTION_STR = None
def ConnectToPostgres(mode):
  import psycopg2
  global REMEMBERED_CONNECTION_STR
  if mode == 'interactive':
    if REMEMBERED_CONNECTION_STR:
      connection_str = REMEMBERED_CONNECTION_STR
    else:
      print('Please enter PostgreSQL URL, or config in JSON format with fields host, database, user and password.')
      connection_str = getpass.getpass()
      REMEMBERED_CONNECTION_STR = connection_str
  elif mode == 'environment':
    connection_str = os.environ.get('LOGICA_PSQL_CONNECTION')
    assert connection_str, (
        'Please provide PSQL connection parameters '
        'in LOGICA_PSQL_CONNECTION.')
  else:
    assert False, 'Unknown mode:' + mode
  if connection_str.startswith('postgres'):
    connection = psycopg2.connect(connection_str)
  else:
    connection_json = json.loads(connection_str)
    connection = psycopg2.connect(**connection_json)

  connection.autocommit = True
  return connection