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

# Utility to run pipeline in terminal with ASCII art showing progress.

import json
import os
import sys

if not __package__ or '.' not in __package__:
  from common import concertina_lib
  from compiler import universe
  from parser_py import parse
  from common import psql_logica
  from common import sqlite3_logica
  from compiler import functors
  from compiler import rule_translate
  from type_inference.research import infer
else:
  from ..common import concertina_lib
  from ..compiler import universe
  from ..parser_py import parse
  from ..common import psql_logica
  from ..common import sqlite3_logica
  from ..compiler import functors
  from ..compiler import rule_translate
  from ..type_inference.research import infer

class SqlRunner(object):
  def __init__(self, engine):
    self.engine = engine
    assert engine in ['sqlite', 'bigquery', 'psql', 'duckdb']
    if engine == 'sqlite':
      self.connection = sqlite3_logica.SqliteConnect()
    else:
      self.connection = None
    if engine == 'bigquery':
      # To install:
      # python3 -m pip install google-auth
      from google import auth
      # To authenticate:
      # gcloud auth application-default login --project=${MY_PROJECT}
      credentials, project = auth.default()
    else:
      credentials, project = None, None
    if engine == 'psql':
      self.connection = psql_logica.ConnectToPostgres('environment')
    if engine == 'duckdb':
      self.connection = None  # No connection needed!
    self.bq_credentials = credentials
    self.bq_project = project
  
  # TODO: Sqlite runner should not be accepting an engine.
  def __call__(self, sql, engine, is_final):
    return RunSQL(sql, engine, self.connection, is_final,
                  self.bq_credentials, self.bq_project)


def RunSQL(sql, engine, connection=None, is_final=False,
           bq_credentials=None, bq_project=None):
  if engine == 'bigquery':
    from google.cloud import bigquery
    client = bigquery.Client(credentials=bq_credentials,
                             project=bq_project)
    df = client.query(sql).to_dataframe()
    # Another way to query BQ:
    # import pandas
    # pandas.read_gbq(sql, project_id=bq_project_id)
    return list(df.columns), [list(r) for _, r in df.iterrows()]
  elif engine == 'psql':
    if is_final:
      cursor = psql_logica.PostgresExecute(sql, connection)
      rows = [list(map(psql_logica.DigestPsqlType, row))
              for row in cursor.fetchall()]
      return [d[0] for d in cursor.description], rows
    else:
      psql_logica.PostgresExecute(sql, connection)
  elif engine == 'sqlite':
    try:
      if is_final:
        cursor = connection.execute(sql)
        header = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
        return header, rows
      else:
        connection.executescript(sql)
    except Exception as e:
      print("\n--- SQL ---")
      print(sql)
      print("Error while executing SQL:\n%s" % e)
      raise e
  elif engine == 'duckdb':
    import duckdb
    if is_final:
      import duckdb
      cur = duckdb.sql(sql)
      return cur.columns, cur.fetchall()
    else:
      duckdb.sql(sql)
    
  else:
    raise Exception('Logica only supports BigQuery, PostgreSQL and SQLite '
                    'for now.')


def Run(filename, predicate_name,
        output_format='artistic_table', display_mode='terminal'):
  try:
    rules = parse.ParseFile(open(filename).read())['rule']
  except parse.ParsingException as parsing_exception:
    parsing_exception.ShowMessage()
    sys.exit(1)


  try:
    program = universe.LogicaProgram(rules)
    engine = program.annotations.Engine()

    # This is needed to build the program execution.
    unused_sql = program.FormattedPredicateSql(predicate_name)

    (header, rows) = concertina_lib.ExecuteLogicaProgram(
        [program.execution], SqlRunner(engine), engine,
        display_mode=display_mode)[predicate_name]
  except rule_translate.RuleCompileException as rule_compilation_exception:
    rule_compilation_exception.ShowMessage()
    sys.exit(1)
  except functors.FunctorError as functor_exception:
    functor_exception.ShowMessage()
    sys.exit(1)
  except infer.TypeErrorCaughtException as type_error_exception:
    type_error_exception.ShowMessage()
    sys.exit(1)

  if output_format == 'artistic_table':
    artistic_table = sqlite3_logica.ArtisticTable(header, rows)
    return artistic_table
  elif output_format == 'header_rows':
    return header, rows
  else:
    assert False, 'Unknown output format: %s' % output_format
