import sqlite3
import unittest
from typing import Dict

from type_inference.type_inference_service import TypeInference
from type_inference.types.edge import Equality
from type_inference.types.expression import Variable, PredicateAddressing
from type_inference.types.types_graph import TypesGraph
from type_inference.types.variable_types import NumberType

number = NumberType()


def create_table(table_name: str, columns: Dict[str, str]):
  conn = sqlite3.connect('logica.db')
  columns_to_create = ', '.join([f'{column[0]} {column[1]}' for column in columns.items()])
  conn.cursor().execute(f'create table if not exists {table_name} (id integer, {columns_to_create})').fetchall()
  conn.close()


def safe_drop_table(table_name: str):
  conn = sqlite3.connect('logica.db')
  conn.cursor().execute(f'drop table if exists {table_name}').fetchall()
  conn.close()


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

    TypeInference(graphs, '../tests/logica.db').Infer()

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

    with self.assertRaises(KeyError):
      TypeInference(graphs, '../tests/logica.db').Infer()

    safe_drop_table('T')
