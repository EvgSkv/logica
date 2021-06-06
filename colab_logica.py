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

from .common import color
from .common import concertina_lib

from .compiler import rule_translate
from .compiler import universe

import IPython

from IPython.core.magic import register_cell_magic
from IPython.display import display

import os

import pandas

from .parser_py import parse
from .common import sqlite3_logica

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

def SetProject(project):
  global PROJECT
  PROJECT = project

def SetDbConnection(connection):
  global DB_CONNECTION
  DB_CONNECTION = connection

def EnsureAuthenticatedUser():
  global USER_AUTHENTICATED
  global PROJECT
  if USER_AUTHENTICATED:
    return
  auth.authenticate_user()
  if PROJECT is None:
    print("Please enter project_id to use for BigQuery querries.")
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


def RunSQL(sql, engine, connection=None, is_final=False):
  if engine == 'bigquery':
    EnsureAuthenticatedUser()
    client = bigquery.Client(project=PROJECT)
    return client.query(sql).to_dataframe()
  elif engine == 'psql':
    if is_final:
      return pandas.read_sql(sql, connection)
    else:
      return connection.execute(sql)
  elif engine == 'sqlite':
    statements = parse.SplitRaw(sql, ';')
    connection.executescript(sql)
    if is_final:
      return pandas.read_sql(statements[-1], connection)
    else:
      pass
    return None
  else:
    raise Exception('Logica only supports BigQuery, PostgreSQL and SQLite '
                    'for now.')


class SqliteRunner(object):
  def __init__(self):
    self.connection = sqlite3_logica.SqliteConnect()
  
  # TODO: Sqlite runner should not be accepting an engine.
  def __call__(self, sql, engine, is_final):
    return RunSQL(sql, engine, self.connection, is_final)


class PostgresRunner(object):
  def __init__(self):
    global DB_CONNECTION
    global DB_ENGINE
    if DB_CONNECTION:
      self.engine = DB_ENGINE
      self.connection = DB_CONNECTION
    else:
      (self.engine, self.connection) = PostgresJumpStart()
      DB_ENGINE = self.engine
      DB_CONNECTION = self.connection
  
  def  __call__(self, sql, engine, is_final):
    return RunSQL(sql, engine, self.connection, is_final)


def Logica(line, cell, run_query):
  """Running Logica predicates and storing results."""
  predicates = ParseList(line)
  try:
    parsed_rules = parse.ParseFile(cell)['rule']
  except parse.ParsingException as e:
    e.ShowMessage()
    return
  program = universe.LogicaProgram(parsed_rules)
  engine = program.annotations.Engine()

  if engine == 'bigquery' and not BQ_READY:
    print(color.Format(
      '[ {error}Error{end} ] BigQuery client and/or authentification is not installed. \n'
      'It is the easiest to run BigQuery requests from Google CoLab:\n'
      '  https://colab.research.google.com/.\n'
      'Note that running Logica on SQLite requires no installation.\n'
      'This could be a good fit for working with small data or learning Logica.\n'
      'Use {warning}@Engine("sqlite");{end} annotation in your program to use SQLite.'))
    return

  bar = TabBar(predicates + ['(Log)'])
  logs_idx = len(predicates)

  executions = []
  sub_bars = []
  ip = IPython.get_ipython()
  for idx, predicate in enumerate(predicates):
    with bar.output_to(logs_idx):
      try:
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
    else:
      sql_runner = RunSQL
    result_map = concertina_lib.ExecuteLogicaProgram(
      executions, sql_runner=sql_runner, sql_engine=engine)

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
from sqlalchemy import create_engine
import pandas
engine = create_engine('postgresql+psycopg2://logica:logica@127.0.0.1', pool_recycle=3600);
connection = engine.connect();
colab_logica.SetDbConnection(connection)""")
    return
  print('Installation succeeded. Connecting...')
  # Connect to the database.
  from logica import colab_logica
  from sqlalchemy import create_engine
  import pandas
  engine = create_engine('postgresql+psycopg2://logica:logica@127.0.0.1', pool_recycle=3600)
  connection = engine.connect()
  print('Connected.')
  return engine, connection