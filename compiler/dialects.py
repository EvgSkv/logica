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

if '.' not in __package__:
  from compiler.dialect_libraries import bq_library
  from compiler.dialect_libraries import psql_library
  from compiler.dialect_libraries import sqlite_library
else:
  from ..compiler.dialect_libraries import bq_library
  from ..compiler.dialect_libraries import psql_library
  from ..compiler.dialect_libraries import sqlite_library

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
    }

  def Subscript(self, record, subscript):
    return '%s.%s' % (record, subscript)
  
  def LibraryProgram(self):
    return bq_library.library


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

  def Subscript(self, record, subscript):
    return '%s.%s' % (record, subscript)
  
  def LibraryProgram(self):
    return sqlite_library.library


class PostgreSQL(Dialect):
  """PostgreSQL SQL dialect."""

  def Name(self):
    return 'PostgreSQL'

  def BuiltInFunctions(self):
    return {
        'Range': '(SELECT ARRAY_AGG(x) FROM GENERATE_SERIES(0, {0} - 1) as x)',
        'ToString': 'CAST(%s AS TEXT)'
      }

  def InfixOperators(self):
    return {
        '++': 'CONCAT(%s, %s)',
    }

  def Subscript(self, record, subscript):
    return '(%s).%s' % (record, subscript)
  
  def LibraryProgram(self):
    return psql_library.library

DIALECTS = {
    'bigquery': BigQueryDialect,
    'sqlite': SqLiteDialect,
    'psql': PostgreSQL
}

