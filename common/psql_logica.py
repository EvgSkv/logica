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
  e = a[0]
  if isinstance(e, tuple):
    return [PsqlTypeAsDictionary(i) for i in a]
  else:
    return a
