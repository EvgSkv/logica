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

"""SQL dialects."""


def Get(engine):
  return DIALECTS[engine]()


class Dialect(object):
  pass


class BigQueryDialect(Dialect):
  """BigQuery SQL dialect."""

  def Name(self):
    return 'BigQuery'

  def BuiltInFunctions(self):
    return {}

  def InfixOperators(self):
    return {
        '++': 'CONCAT(%s, %s)',
        '->': 'STRUCT(%s AS arg, %s as value)',
    }


class SqLiteDialect(Dialect):
  """SqLite SQL dialect."""

  def Name(self):
    return 'SqLite'

  def BuiltInFunctions(self):
    return {
        'Set': None
    }

  def InfixOperators(self):
    return {
        '++': '(%s) || (%s)',
    }

class PostgreSQL(Dialect):
  """PostgreSQL SQL dialect."""

  def Name(self):
    return 'PostgreSQL'

  def BuiltInFunctions(self):
    return {
        'ArgMax': '(ARRAY_AGG({0}.arg order by {0}.value desc))[1]',
        'ArgMaxK':
            'ARRAY_AGG({0} order by {0}.value desc)',
        'ArgMin': '(ARRAY_AGG({0}.arg order by {0}.value))[1]',
        'ArgMinK':
            'ARRAY_AGG({0} order by {0}.value)',
        'ToString': 'CAST(%s AS TEXT)'
      }

  def InfixOperators(self):
    return {
        '++': 'CONCAT(%s, %s)',
        '->': '(%s, %s)::logica_arrow'
    }

DIALECTS = {
    'bigquery': BigQueryDialect,
    'sqlite': SqLiteDialect,
    'psql': PostgreSQL
}

