#!/usr/bin/python
#
# Copyright 2023 Logica
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
from typing import Dict

from type_inference.inspectors.sqlite_inspector import SQLiteInspector
from type_inference.inspectors.table_not_exist_exception import TableNotExistException
from type_inference.type_inference_service import TypeInference
from type_inference.types.edge import Equality
from type_inference.types.expression import Variable, PredicateAddressing
from type_inference.types.types_graph import TypesGraph
from type_inference.types.variable_types import NumberType

number = NumberType()


def create_table(table_name: str, columns: Dict[str, str]):
  with sqlite3.connect('logica.db') as conn:
    columns_to_create = ', '.join([f'{column[0]} {column[1]}' for column in columns.items()])
    cursor = conn.cursor()
    cursor.execute(f'create table if not exists {table_name} (id integer, {columns_to_create})').fetchall()


def safe_drop_table(table_name: str):
  with sqlite3.connect('logica.db') as conn:
    conn.cursor().execute(f'drop table if exists {table_name}').fetchall()


class TestTypeInferenceWithDb(unittest.TestCase):
  def test_when_linked_with_predicate_from_db(self):
    # 'Q(x) :- T(x)'
    create_table('T', {'col0': 'integer'})
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

    safe_drop_table('T')

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

    with self.assertRaises(TableNotExistException):
      TypeInference(graphs, sqlite_inspector).Infer()

    safe_drop_table('T')
