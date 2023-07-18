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

if not __package__ or '.' not in __package__:
  from common import concertina_lib
  from compiler import universe
  from parser_py import parse
  from common import sqlite3_logica
else:
  from ..common import concertina_lib
  from ..compiler import universe
  from ..parser_py import parse
  from ..common import sqlite3_logica


class SqlRunner(object):
  def __init__(self, engine):
    self.engine = engine
    assert engine in ['sqlite', 'bigquery', 'psql']
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
      import psycopg2
      if os.environ.get('LOGICA_PSQL_CONNECTION'):
        connection_json = json.loads(os.environ.get('LOGICA_PSQL_CONNECTION'))
      else:
        assert False, (
          'Please provide PSQL connection parameters '
          'in LOGICA_PSQL_CONNECTION')
      self.connection = psycopg2.connect(**connection_json)

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
    import pandas
    if is_final:
      cursor = connection.cursor()
      cursor.execute(sql)
      rows = cursor.fetchall()
      df = pandas.DataFrame(
        rows, columns=[d[0] for d in cursor.description])
      connection.close()
      return list(df.columns), [list(r) for _, r in df.iterrows()]
    else:
      cursor = connection.cursor()
      cursor.execute(sql)
      connection.commit()
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
  else:
    raise Exception('Logica only supports BigQuery, PostgreSQL and SQLite '
                    'for now.')


def Run(filename, predicate_name):
  rules = parse.ParseFile(open(filename).read())['rule']
  program = universe.LogicaProgram(rules)
  engine = program.annotations.Engine()

  # This is needed to build the program execution.
  unused_sql = program.FormattedPredicateSql(predicate_name)

  (header, rows) = concertina_lib.ExecuteLogicaProgram(
      [program.execution], SqlRunner(engine), engine,
      display_mode='terminal')[predicate_name]

  artistic_table = sqlite3_logica.ArtisticTable(header, rows)
  return artistic_table
