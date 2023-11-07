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

from type_inference.postgresql_type_parser import PostgresTypeToLogicaType
import psycopg2

class BuiltInTypeRetriever:
  def __init__(self):
    self.built_in_types = set()
    self.name_to_type = dict()

  def InitBuiltInTypes(self, connection_string: str):
    if self.built_in_types:
      return

    with psycopg2.connect(connection_string) as conn:
      with conn.cursor() as cur:
        # this SQL query returns all primitive types (defined by PostgreSQL directly)
        cur.execute('''
  SELECT t.typname as type
  FROM pg_type t
      LEFT JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
  WHERE n.nspname = 'pg_catalog'
    AND (
      t.typrelid = 0 OR (SELECT c.relkind = 'c'
                         FROM pg_catalog.pg_class c
                         WHERE c.oid = t.typrelid)
    )
    AND NOT EXISTS(
      SELECT 1
      FROM pg_catalog.pg_type el
      WHERE el.oid = t.typelem
        AND el.typarray = t.oid
    );''')
        self.built_in_types.update((t[0] for t in cur.fetchall()))

  def UnpackType(self, udt_type: str, conn) -> str:
    if udt_type in self.built_in_types:
      return PostgresTypeToLogicaType(udt_type)

    if udt_type not in self.name_to_type.keys():
      if udt_type.startswith('_'):
        self.name_to_type[udt_type] = f'[{self.UnpackType(udt_type.lstrip("_"), conn)}]'
      else:
        with conn.cursor() as cur:
          # this SQL query returns all children (= fields) of given udt_type (named by parent_type) and its types
          cur.execute('''
      SELECT pg_attribute.attname AS field_name,
          child_type.typname AS field_type
      FROM pg_type AS parent_type
          JOIN pg_attribute ON pg_attribute.attrelid = parent_type.typrelid
          JOIN pg_type AS child_type ON child_type.oid = pg_attribute.atttypid
      WHERE parent_type.typname = '{%s}';''', (udt_type,))

          fields = (f'{field_name}: {self.UnpackType(field_type, conn)}' for field_name, field_type in cur.fetchall())
          self.name_to_type[udt_type] = '{%s}' % (", ".join(fields))
    return self.name_to_type[udt_type]
