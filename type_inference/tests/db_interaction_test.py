#!/usr/bin/python
#
# Copyright 2023 Logica Authors
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

import sqlite3
import unittest
from typing import Dict, Tuple, List

from sqlalchemy import MetaData, Table, Column, Integer, create_engine

from type_inference.inspectors.postgres_inspector import PostgresInspector
from type_inference.inspectors.sqlite_inspector import SQLiteInspector
from type_inference.inspectors.table_not_exist_exception import TableDoesNotExistException
from type_inference.type_inference_service import TypeInference
from type_inference.types.edge import Equality
from type_inference.types.expression import Variable, PredicateAddressing
from type_inference.types.types_graph import TypesGraph
from type_inference.types.variable_types import NumberType

sqlite_db_file_name = 'logica.db'
number = NumberType()


class TestTypeInferenceWithSqlite(unittest.TestCase):
  @staticmethod
  def create_table(table_name: str, columns: Dict[str, str]):
    with sqlite3.connect(sqlite_db_file_name) as conn:
      columns_to_create = ', '.join([f'{column[0]} {column[1]}' for column in columns.items()])
      cursor = conn.cursor()
      cursor.execute(f'create table if not exists {table_name} (id integer, {columns_to_create})').fetchall()

  @staticmethod
  def safe_drop_table(table_name: str):
    with sqlite3.connect(sqlite_db_file_name) as conn:
      conn.cursor().execute(f'drop table if exists {table_name}').fetchall()

  def test_when_linked_with_predicate_from_db(self):
    # 'Q(x) :- T(x)'
    self.create_table('T', {'col0': 'integer'})
    graph = TypesGraph()
    q_col0 = Variable('col0')
    t_col0 = PredicateAddressing('T', 'col0')
    x_var = Variable('x')
    graph.Connect(Equality(q_col0, x_var, (0, 0)))
    graph.Connect(Equality(x_var, t_col0, (0, 0)))
    graphs = dict()
    graphs['Q'] = graph
    sqlite_inspector = SQLiteInspector('../tests/logica.db')

    TypeInference(graphs, sqlite_inspector).Infer()

    self.assertEquals(q_col0.type, number)
    self.assertEquals(t_col0.type, number)

    self.safe_drop_table('T')

  def test_when_linked_with_unknown_predicate(self):
    # 'Q(x) :- T(x)'
    graph = TypesGraph()
    q_col0 = Variable('col0')
    t_col0 = PredicateAddressing('T', 'col0')
    x_var = Variable('x')
    graph.Connect(Equality(q_col0, x_var, (0, 0)))
    graph.Connect(Equality(x_var, t_col0, (0, 0)))
    graphs = dict()
    graphs['Q'] = graph
    sqlite_inspector = SQLiteInspector('../tests/logica.db')

    with self.assertRaises(TableDoesNotExistException):
      TypeInference(graphs, sqlite_inspector).Infer()


class TestTypeInferenceWithPsql(unittest.TestCase):
  @staticmethod
  def create_table(table_name: str, columns: List[Column]) -> Tuple[MetaData, Table]:
    metadata = MetaData()
    table = Table(table_name, metadata, *columns)
    engine = create_engine(f'postgresql+psycopg2://logica:logica@127.0.0.1', pool_recycle=3600)
    metadata.create_all(engine)
    return metadata, table

  @staticmethod
  def safe_drop_table(metadata: MetaData, table: Table):
    metadata.remove(table)

  def test_when_linked_with_predicate_from_db(self):
    # 'Q(x) :- T(x)'
    metadata, table = self.create_table('T', [Column('col0', Integer, primary_key=True)])
    graph = TypesGraph()
    q_col0 = Variable('col0')
    t_col0 = PredicateAddressing('T', 'col0')
    x_var = Variable('x')
    graph.Connect(Equality(q_col0, x_var, (0, 0)))
    graph.Connect(Equality(x_var, t_col0, (0, 0)))
    graphs = dict()
    graphs['Q'] = graph
    postgres_inspector = PostgresInspector('logica', 'logica')

    TypeInference(graphs, postgres_inspector).Infer()

    self.assertEquals(q_col0.type, number)
    self.assertEquals(t_col0.type, number)

    self.safe_drop_table(metadata, table)

  def test_when_linked_with_unknown_predicate_psql(self):
    # 'Q(x) :- T(x)'
    graph = TypesGraph()
    q_col0 = Variable('col0')
    t_col0 = PredicateAddressing('T', 'col0')
    x_var = Variable('x')
    graph.Connect(Equality(q_col0, x_var, (0, 0)))
    graph.Connect(Equality(x_var, t_col0, (0, 0)))
    graphs = dict()
    graphs['Q'] = graph
    postgres_inspector = PostgresInspector('logica', 'logica')

    with self.assertRaises(TableDoesNotExistException):
      TypeInference(graphs, postgres_inspector).Infer()
