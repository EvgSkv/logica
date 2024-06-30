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

"""Library for using Logica in CoLab."""

from decimal import Decimal
import getpass
import json
import re

from .common import color
from .common import concertina_lib
from .common import psql_logica

from .compiler import functors
from .compiler import rule_translate
from .compiler import universe

from .type_inference.research import infer

import IPython

from IPython.core.magic import register_cell_magic
from IPython.display import display

import os

import pandas
import duckdb

from .parser_py import parse
from .common import sqlite3_logica
from .common import duckdb_logica

BQ_READY = True  # By default.

try:
  from google.cloud import bigquery
except:
  BQ_READY = False
  print('Could not import google.cloud.bigquery.')

try:
  from google.colab import auth
except:
  BQ_READY = False
  print('Could not import google.cloud.auth.')

try:
  from google.colab import widgets
  WIDGETS_IMPORTED = True
except:
  WIDGETS_IMPORTED = False
  print('Could not import google.colab.widgets.')

PROJECT = None

# TODO: Should this be renamed to PSQL_ENGINE, PSQL_CONNECTION?
DB_ENGINE = None
DB_CONNECTION = None

USER_AUTHENTICATED = False

TABULATED_OUTPUT = True

SHOW_FULL_QUERY = True

PREAMBLE = None

if hasattr(concertina_lib, 'graphviz'):
  DISPLAY_MODE = 'colab'
else:
  DISPLAY_MODE = 'colab-text'

DEFAULT_ENGINE = 'bigquery'


def SetPreamble(preamble):
  global PREAMBLE
  PREAMBLE = preamble

def SetProject(project):
  global PROJECT
  PROJECT = project

def SetDbConnection(connection):
  global DB_CONNECTION
  DB_CONNECTION = connection

REMEMBERED_PREVIOUS_MODE = None
def ConnectToPostgres(mode='interactive'):
  global REMEMBERED_PREVIOUS_MODE
  if mode == 'reconnect':
    mode = REMEMBERED_PREVIOUS_MODE
    print('Reconnecting to Postgres.')
  else:
    REMEMBERED_PREVIOUS_MODE = mode
  connection = psql_logica.ConnectToPostgres(mode)
  SetDbConnection(connection)
  global DEFAULT_ENGINE
  DEFAULT_ENGINE = 'psql'

def EnsureAuthenticatedUser():
  global USER_AUTHENTICATED
  global PROJECT
  if USER_AUTHENTICATED:
    return
  auth.authenticate_user()
  if PROJECT is None:
    print("Please enter project_id to use for BigQuery queries.")
    PROJECT = input()
    print("project_id is set to %s" % PROJECT)
    print("You can change it with logica.colab_logica.SetProject command.")
  USER_AUTHENTICATED = True

def SetTabulatedOutput(tabulated_output):
  global TABULATED_OUTPUT
  global SHOW_FULL_QUERY
  TABULATED_OUTPUT = tabulated_output
  SHOW_FULL_QUERY = TABULATED_OUTPUT

if not WIDGETS_IMPORTED:
  SetTabulatedOutput(False)

def TabBar(*args):
  """Returns a real TabBar or a mock. Useful for UIs that don't support JS."""
  if TABULATED_OUTPUT:
    return widgets.TabBar(*args)
  class MockTab:
      def __init__(self):
          pass
      def __enter__(self):
          pass
      def __exit__(self, *x):
          pass
  class MockTabBar:
      def __init__(self):
          pass
      def output_to(self, x):
          return MockTab()
  return MockTabBar()

@register_cell_magic
def logica(line, cell):
  Logica(line, cell, run_query=True)


def ParseList(line):
  line = line.strip()
  if not line:
    predicates = []
  else:
    predicates = [p.strip() for p in line.split(',')]
  return predicates

def ParseListAndMaybeFile(line):
  if '>' in line:
    predicate_list_str, storage_file = line.split('>')
    return ParseList(predicate_list_str.strip()), storage_file.strip()
  else:
    return ParseList(line), None

def RunSQL(sql, engine, connection=None, is_final=False):
  if engine == 'bigquery':
    client = bigquery.Client(project=PROJECT)
    return client.query(sql).to_dataframe()
  elif engine == 'psql':
    if is_final:
      cursor = psql_logica.PostgresExecute(sql, connection)
      rows = cursor.fetchall()
      df = pandas.DataFrame(
        rows, columns=[d[0] for d in cursor.description])
      df = df.applymap(psql_logica.DigestPsqlType)
      return df
    else:
      psql_logica.PostgresExecute(sql, connection)
  elif engine == 'duckdb':
    if is_final:
      df = connection.sql(sql).df()
      for c in df.columns:
        if df.dtypes[c] == 'float64':
          if df[c].isna().values.any():
            return df
          if set(df[c] - df[c].astype(int)) == {0.0}:
            df[c] = df[c].astype(int)
      return df
    else:
      connection.sql(sql)
  elif engine == 'sqlite':
    try:
      if is_final:
        # For final predicates this SQL is always a single statement.
        return pandas.read_sql(sql, connection)
      else:
        connection.executescript(sql)
    except Exception as e:
      print("\n--- SQL ---")
      print(sql)
      ShowError("Error while executing SQL:\n%s" % e)
      raise e
    return None
  else:
    raise Exception('Logica only supports BigQuery, PostgreSQL and SQLite '
                    'for now.')


def Ingress(table_name, csv_file_name):
  with open(csv_file_name) as csv_data_io:
    cursor = DB_CONNECTION.cursor()
    cursor.copy_expert(
      'COPY %s FROM STDIN WITH CSV HEADER' % table_name,
      csv_data_io)
    DB_CONNECTION.commit()


class SqliteRunner(object):
  def __init__(self):
    self.connection = sqlite3_logica.SqliteConnect()
  
  # TODO: Sqlite runner should not be accepting an engine.
  def __call__(self, sql, engine, is_final):
    return RunSQL(sql, engine, self.connection, is_final)

class DuckdbRunner(object):
  def __init__(self):
    global DB_CONNECTION
    if not DB_CONNECTION:
      DB_CONNECTION = duckdb.connect()
    self.connection = DB_CONNECTION

  def  __call__(self, sql, engine, is_final):
    return RunSQL(sql, engine, self.connection, is_final)


class PostgresRunner(object):
  def __init__(self):
    global DB_CONNECTION
    global DB_ENGINE
    if not DB_CONNECTION:
      try:
        ConnectToLocalPostgres()  
      except:
        pass

    if not DB_CONNECTION:
      print("Assuming this is running on Google CoLab in a temporary")
      print("environment.")
      print("Would you like to install and run postgres?")
      user_choice = input('y or N? ')
      if user_choice != 'y':
        print('User declined.')
        print('Bailing out.')
        return
      PostgresJumpStart()
    self.connection = DB_CONNECTION
  
  def  __call__(self, sql, engine, is_final):
    global DB_CONNECTION
    if self.connection and self.connection.closed and REMEMBERED_PREVIOUS_MODE:
      ConnectToPostgres('reconnect')
      self.connection = DB_CONNECTION
    return RunSQL(sql, engine, self.connection, is_final)


def ShowError(error_text):
  print(color.Format('[ {error}Error{end} ] ' + error_text))


def Logica(line, cell, run_query):
  """Running Logica predicates and storing results."""
  predicates, maybe_storage_file = ParseListAndMaybeFile(line)
  if not predicates:
    ShowError('No predicates to run.')
    return
  try:
    program = ';\n'.join(s for s in [PREAMBLE, cell] if s)
    parsed_rules = parse.ParseFile(program)['rule']
  except parse.ParsingException as e:
    e.ShowMessage()
    return
  try:
    program = universe.LogicaProgram(
        parsed_rules,
        user_flags={'logica_default_engine': DEFAULT_ENGINE})
  except functors.FunctorError as e:
    e.ShowMessage()
    return
  except rule_translate.RuleCompileException as e:
    e.ShowMessage()
    return
  except infer.TypeErrorCaughtException as e:
    e.ShowMessage()
    return
  engine = program.annotations.Engine()

  if engine == 'bigquery' and not BQ_READY:
    ShowError(
      'BigQuery client and/or authentification is not installed. \n'
      'It is the easiest to run BigQuery requests from Google CoLab:\n'
      '  https://colab.research.google.com/.\n'
      'Note that running Logica on SQLite requires no installation.\n'
      'This could be a good fit for working with small data or learning Logica.\n'
      'Use {warning}@Engine("sqlite");{end} annotation in your program to use SQLite.')
    return

  bar = TabBar(predicates + ['(Log)'])
  logs_idx = len(predicates)
  executions = []
  sub_bars = []
  ip = IPython.get_ipython()
  for idx, predicate in enumerate(predicates):
    with bar.output_to(logs_idx):
      try:
        if storage_file_name := maybe_storage_file:
          with open(storage_file_name, 'w') as storage_file:
            storage_file.write(cell)
            print('\x1B[3mProgram saved to %s.\x1B[0m' % storage_file_name)
        sql = program.FormattedPredicateSql(predicate)
        executions.append(program.execution)
        ip.push({predicate + '_sql': sql})
      except rule_translate.RuleCompileException as e:
        print('Encountered error when compiling %s.' % predicate)
        e.ShowMessage()
        return
    # Publish output to Colab cell.
    with bar.output_to(idx):
      sub_bar = TabBar(['SQL', 'Result'])
      sub_bars.append(sub_bar)
      with sub_bar.output_to(0):
        if SHOW_FULL_QUERY:
          print(
              color.Format(
                  'The following query is stored at {warning}%s{end} '
                  'variable.' % (
                      predicate + '_sql')))
          print(sql)
        else:
          print('Query is stored at %s variable.' %
                color.Warn(predicate + '_sql'))

  with bar.output_to(logs_idx):
    if engine == 'sqlite':
      sql_runner = SqliteRunner()
    elif engine == 'psql':
      sql_runner = PostgresRunner()
    elif engine == 'duckdb':
      sql_runner = DuckdbRunner() 
    elif engine == 'bigquery':
      EnsureAuthenticatedUser()
      sql_runner = RunSQL
    else:
      raise Exception('Logica only supports BigQuery, PostgreSQL and SQLite '
                      'for now.')   
    try:
      result_map = concertina_lib.ExecuteLogicaProgram(
        executions, sql_runner=sql_runner, sql_engine=engine,
        display_mode=DISPLAY_MODE)
    except infer.TypeErrorCaughtException as e:
      e.ShowMessage()
      return

  for idx, predicate in enumerate(predicates):
    t = result_map[predicate]
    ip.push({predicate: t})
    with bar.output_to(idx):
      with sub_bars[idx].output_to(1): 
        if run_query:
          print(
              color.Format(
                  'The following table is stored at {warning}%s{end} '
                  'variable.' %
                  predicate))
          display(t)  
        else:
          print('The query was not run.')
      print(' ') # To activate the tabbar.


def ConnectToLocalPostgres():
  import psycopg2
  connection = psycopg2.connect(host='localhost', database='logica', user='logica', password='logica')
  connection.autocommit = True

  print('Connected.')
  global DEFAULT_ENGINE
  global DB_CONNECTION
  DEFAULT_ENGINE = 'psql'
  DB_CONNECTION = connection


def PostgresJumpStart():
  # Install postgresql server.
  print("Installing and configuring an empty PostgreSQL database.")
  result = 0
  result += os.system('sudo apt-get -y -qq update')
  result += os.system('sudo apt-get -y -qq install postgresql')
  result += os.system('sudo service postgresql start')
  # Ignoring user creation error, as they may already exist.
  result += 0 * os.system(
    'sudo -u postgres psql -c "CREATE USER logica WITH SUPERUSER"')
  result += os.system(
    'sudo -u postgres psql -c "ALTER USER logica PASSWORD \'logica\';"')
  result += os.system(
    'sudo -u postgres psql -U postgres -c \'CREATE DATABASE logica;\'')
  if result != 0:
    print("""Installation failed. Please try the following manually:
# Install Logica.
!pip install logica

# Install postgresql server.
!sudo apt-get -y -qq update
!sudo apt-get -y -qq install postgresql
!sudo service postgresql start

# Prepare database for Logica.
!sudo -u postgres psql -c "CREATE USER logica WITH SUPERUSER"
!sudo -u postgres psql -c "ALTER USER logica PASSWORD 'logica';"
!sudo -u postgres psql -U postgres -c 'CREATE DATABASE logica;'

# Connect to the database.
from logica import colab_logica
import psycopg2
connection = psycopg2.connect(host='localhost', database='logica', user='logica', password='logica')
connection.autocommit = True
colab_logica.DEFAULT_ENGINE = 'psql'
colab_logica.SetDbConnection(connection)
""")
    return
  print('Installation succeeded. Connecting...')
  # Connect to the database.
  ConnectToLocalPostgres()
