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

import copy

if '.' not in __package__:
  from compiler.dialect_libraries import bq_library
  from compiler.dialect_libraries import psql_library
  from compiler.dialect_libraries import sqlite_library
  from compiler.dialect_libraries import trino_library
  from compiler.dialect_libraries import presto_library
  from compiler.dialect_libraries import databricks_library
  from compiler.dialect_libraries import duckdb_library
else:
  from ..compiler.dialect_libraries import bq_library
  from ..compiler.dialect_libraries import psql_library
  from ..compiler.dialect_libraries import sqlite_library
  from ..compiler.dialect_libraries import trino_library
  from ..compiler.dialect_libraries import presto_library
  from ..compiler.dialect_libraries import databricks_library
  from ..compiler.dialect_libraries import duckdb_library
def Get(engine):
  return DIALECTS[engine]()


class Dialect(object):
  pass

  # Default methods:
  def MaybeCascadingDeletionWord(self):
    return ''  # No CASCADE is needed by default.
  
  def PredicateLiteral(self, predicate_name):
    return "'predicate_name:%s'" % predicate_name

  def IsPostgreSQLish(self):
    return False

class BigQueryDialect(Dialect):
  """BigQuery SQL dialect."""

  def Name(self):
    return 'BigQuery'

  def BuiltInFunctions(self):
    return {}

  def InfixOperators(self):
    return {
        '++': '%s || %s',
    }

  def Subscript(self, record, subscript, record_is_table):
    return '%s.%s' % (record, subscript)

  def LibraryProgram(self):
    return bq_library.library

  def UnnestPhrase(self):
    return 'UNNEST({0}) as {1}'

  def ArrayPhrase(self):
    return 'ARRAY[%s]'

  def GroupBySpecBy(self):
    return 'name'

  def DecorateCombineRule(self, rule, var):
    return rule

  def PredicateLiteral(self, predicate_name):
    return 'STRUCT("%s" AS predicate_name)' % predicate_name

  
class SqLiteDialect(Dialect):
  """SqLite SQL dialect."""

  def Name(self):
    return 'SqLite'

  def BuiltInFunctions(self):
    return {
        'Set': 'DistinctListAgg({0})',
        'Element': "JSON_EXTRACT({0}, '$[' || {1} || ']')",
        'Range': ('(select json_group_array(n) from (with recursive t as'
                  '(select 0 as n union all '
                  'select n + 1 as n from t where n + 1 < {0}) '
                  'select n from t) where n < {0})'),
        'ValueOfUnnested': '{0}.value',
        'List': 'JSON_GROUP_ARRAY({0})',
        'Size': 'JSON_ARRAY_LENGTH({0})',
        'Join': 'JOIN_STRINGS({0}, {1})',
        'Count': 'COUNT(DISTINCT {0})',
        'StringAgg': 'GROUP_CONCAT(%s)',
        'Sort': 'SortList({0})',
        'MagicalEntangle': 'MagicalEntangle({0}, {1})',
        'Format': 'Printf(%s)',
        'Least': 'MIN(%s)',
        'Greatest': 'MAX(%s)',
        'ToString': 'CAST(%s AS TEXT)',
        'DateAddDay': "DATE({0}, {1} || ' days')",
        'DateDiffDay': "CAST(JULIANDAY({0}) - JULIANDAY({1}) AS INT64)"
    }

  def DecorateCombineRule(self, rule, var):
    return DecorateCombineRule(rule, var)

  def InfixOperators(self):
    return {
        '++': '(%s) || (%s)',
        '%' : '(%s) %% (%s)',
        'in': 'IN_LIST(%s, %s)'
    }

  def Subscript(self, record, subscript, record_is_table):
    if record_is_table:
      return '%s.%s' % (record, subscript)
    else:
      return 'JSON_EXTRACT(%s, "$.%s")' % (record, subscript)
  
  def LibraryProgram(self):
    return sqlite_library.library

  def UnnestPhrase(self):
    return 'JSON_EACH({0}) as {1}'

  def ArrayPhrase(self):
    return 'JSON_ARRAY(%s)'

  def GroupBySpecBy(self):
    return 'expr'

class PostgreSQL(Dialect):
  """PostgreSQL SQL dialect."""

  def Name(self):
    return 'PostgreSQL'

  def BuiltInFunctions(self):
    return {
        'Range': '(SELECT ARRAY_AGG(x) FROM GENERATE_SERIES(0, {0} - 1) as x)',
        'RangeOf' : '(SELECT ARRAY_AGG(x) FROM GENERATE_SERIES(0, ARRAY_LENGTH({0}, 1) - 1) as x)',
        'ToString': 'CAST(%s AS TEXT)',
        'ToInt64': 'CAST(%s AS BIGINT)',
        'Element': '({0})[{1} + 1]',
        'Size': 'COALESCE(ARRAY_LENGTH({0}, 1), 0)',
        'Count': 'COUNT(DISTINCT {0})',
        'MagicalEntangle': '(CASE WHEN {1} = 0 THEN {0} ELSE NULL END)',
        'ArrayConcat': '{0} || {1}',
        'Split': 'STRING_TO_ARRAY({0}, {1})',
        'AnyValue': '(ARRAY_AGG(%s))[1]'
      }

  def InfixOperators(self):
    return {
        '++': '%s || %s',  # Works for strings and lists.
        'in': '%s = ANY(%s)'
    }

  def Subscript(self, record, subscript, record_is_table):
    return '(%s).%s' % (record, subscript)

  def LibraryProgram(self):
    return psql_library.library

  def UnnestPhrase(self):
    return 'UNNEST({0}) as {1}'

  def ArrayPhrase(self):
    return 'ARRAY[%s]'

  def GroupBySpecBy(self):
    return 'expr'

  def DecorateCombineRule(self, rule, var):
    return DecorateCombineRule(rule, var)
  
  def MaybeCascadingDeletionWord(self):
    return ' CASCADE'  # Need to cascade in PSQL.
  
  def IsPostgreSQLish(self):
    return True


class Trino(Dialect):
  """Trino analytic engine dialect."""

  def Name(self):
    return 'Trino'

  def BuiltInFunctions(self):
    return {
        'Range': 'SEQUENCE(0, %s - 1)',
        'ToString': 'CAST(%s AS VARCHAR)',
        'ToInt64': 'CAST(%s AS BIGINT)',
        'ToFloat64': 'CAST(%s AS DOUBLE)',
        'AnyValue': 'ARBITRARY(%s)',
        'ArrayConcat': '{0} || {1}'
    }

  def InfixOperators(self):
    return {
        '++': 'CONCAT(%s, %s)',
    }

  def Subscript(self, record, subscript, record_is_table):
    return '%s.%s' % (record, subscript)

  def LibraryProgram(self):
    return trino_library.library

  def UnnestPhrase(self):
    return 'UNNEST({0}) as pushkin({1})'

  def ArrayPhrase(self):
    return 'ARRAY[%s]'

  def GroupBySpecBy(self):
    return 'index'

  def DecorateCombineRule(self, rule, var):
    return rule


class Presto(Dialect):

  def Name(self):
    return 'Presto'

  def BuiltInFunctions(self):
    return {
        'Range': 'SEQUENCE(0, %s - 1)',
        'ToString': 'CAST(%s AS VARCHAR)',
        'ToInt64': 'CAST(%s AS BIGINT)',
        'ToFloat64': 'CAST(%s AS DOUBLE)',
        'AnyValue': 'ARBITRARY(%s)'
    }

  def InfixOperators(self):
    return {
        '++': 'CONCAT(%s, %s)',
    }

  def Subscript(self, record, subscript, record_is_table):
    return '%s.%s' % (record, subscript)

  def LibraryProgram(self):
    return presto_library.library

  def UnnestPhrase(self):
    return 'UNNEST({0}) as pushkin({1})'

  def ArrayPhrase(self):
    return 'ARRAY[%s]'

  def GroupBySpecBy(self):
    return 'index'

  def DecorateCombineRule(self, rule, var):
    return rule

def DecorateCombineRule(rule, var):
  """Resolving ambiguity of aggregation scope."""
  # Entangling result of aggregation with a variable that comes from a list
  # unnested inside a combine expression, to make it clear that aggregation
  # must be done in the combine. 
  rule = copy.deepcopy(rule)

  rule['head']['record']['field_value'][0]['value'][
    'aggregation']['expression']['call'][
    'record']['field_value'][0]['value'] = (
    {
      'expression': {
        'call': {
          'predicate_name': 'MagicalEntangle',
          'record': {
            'field_value': [
              {
                'field': 0,
                'value': rule['head']['record']['field_value'][0]['value'][
                  'aggregation']['expression']['call'][
                    'record']['field_value'][0]['value']      
              },
              {
                'field': 1,
                'value': {
                  'expression': {
                    'variable': {
                      'var_name': var
                    }
                  }
                }
              }
            ]
          }
        }
      }
    }
  )

  if 'body' not in rule:
    rule['body'] = {'conjunction': {'conjunct': []}}
  rule['body']['conjunction']['conjunct'].append(
    {
      "inclusion": {
        "list": {
          "literal": {
            "the_list": {
              "element": [
                {
                  "literal": {
                    "the_number": {
                      "number": "0"
                    }
                  }
                }
              ]
            }
          }
        },
        "element": {
          "variable": {
            "var_name": var
          }
        }
      }
    }      
  )
  return rule

class Databricks(Dialect):
    """Databricks dialect"""

    #TODO: add DATEDIFF and NOW function

    def Name(self):
        return 'Databricks'

    def BuiltInFunctions(self):
        return {
            'ToString': 'CAST(%s AS STRING)',
            'ToInt64': 'CAST(%s AS BIGINT)',
            'ToFloat64': 'CAST(%s AS DOUBLE)',
            'AnyValue': 'ANY_VALUE(%s)',
            'ILike': '({0}::string ILIKE {1})',
            'Like': '({0}::string LIKE {1})',
            'Replace': 'REPLACE({0}::string, {1}, {2})',
            'ArrayConcat': 'ARRAY_JOIN({0}, {1})',
            'JsonExtract': 'GET_JSON_OBJECT({0}, {1})',
            'JsonExtractScalar': 'GET_JSON_OBJECT({0}, {1})',
            'Length': 'ARRAY_SIZE(%s)',
            'DateDiff': 'DATEDIFF({0}, {1}, {2})',
            'IsNull': '({0} IS NULL)',
            'LogicalOr': 'BOOL_OR(%s)',
            'LogicalAnd': 'BOOL AND(%s)'
        }

    def InfixOperators(self):
        return {
            '++': 'CONCAT(%s, %s)',
            'in': 'ARRAY_CONTAINS(%s, %s)'
        }

    def Subscript(self, record, subscript):
        return '%s.%s' % (record, subscript)

    def LibraryProgram(self):
        return databricks_library.library

    def UnnestPhrase(self):
        return 'explode({0}) AS pushkin({1})'

    def ArrayPhrase(self):
        return 'ARRAY(%s)'

    def GroupBySpecBy(self):
        return 'index'

    def DecorateCombineRule(self, rule, var):
        return rule

class DuckDB(Dialect):
    """DuckDB dialect"""

    def Name(self):
      return 'DuckDB'

    def BuiltInFunctions(self):
      return {
          'Element': "array_extract({0},  CAST({1}+1 AS BIGINT))",
          'Range': 'Range({0})',
          'ValueOfUnnested': '{0}.unnested_pod',
          'Size': 'LEN({0})',
          'Join': 'ARRAY_TO_STRING({0}, {1})',
          'Count': 'COUNT(DISTINCT {0})',
          'StringAgg': 'GROUP_CONCAT(%s)',
          'Sort': 'SortList({0})',
          'MagicalEntangle': '(CASE WHEN {1} = 0 THEN {0} ELSE NULL END)',
          'Format': 'Printf(%s)',
          'Least': 'LEAST(%s)',
          'Greatest': 'GREATEST(%s)',
          'ToString': 'CAST(%s AS TEXT)',
          'ToFloat64': 'CAST(%s AS DOUBLE)',
          'DateAddDay': "DATE({0}, {1} || ' days')",
          'DateDiffDay': "CAST(JULIANDAY({0}) - JULIANDAY({1}) AS INT64)",
          'CurrentTimestamp': 'GET_CURRENT_TIMESTAMP()',
          'TimeAdd': '{0} + to_microseconds(cast(1000000 * {1} as int64))'
      }

    def DecorateCombineRule(self, rule, var):
      return DecorateCombineRule(rule, var)

    def InfixOperators(self):
      return {
          '++': '(%s) || (%s)',
          '%' : '(%s) %% (%s)',
          'in': 'list_contains({right}, {left})'
      }

    def Subscript(self, record, subscript, record_is_table):
      return '%s.%s' % (record, subscript)

    def LibraryProgram(self):
      return duckdb_library.library

    def UnnestPhrase(self):
      return '(select unnest({0}) as unnested_pod) as {1}'

    def ArrayPhrase(self):
      return '[%s]'

    def GroupBySpecBy(self):
      return 'expr'
    
    def IsPostgreSQLish(self):
      return True


DIALECTS = {
    'bigquery': BigQueryDialect,
    'sqlite': SqLiteDialect,
    'psql': PostgreSQL,
    'presto': Presto,
    'trino': Trino,
    'databricks': Databricks,
    'duckdb': DuckDB,
}

