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

from typing import Dict
from type_inference.postgresql_type_parser import PostgresTypeToLogicaType
import psycopg2


class TypeRetriever:
  def __init__(self):
    self.built_in_types = set()
    self.name_to_type_cache = dict()

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

  def UnpackTypeByCachesOnly(self, udt_type: str) -> str | None:
    if udt_type[0] == '_':
      single_value_type = self.UnpackTypeByCachesOnly(udt_type[1:])

      if not single_value_type:
        return None

      self.name_to_type_cache[udt_type] = f'[{self.UnpackTypeByCachesOnly(udt_type[1:])}]'
      return self.name_to_type_cache[udt_type]

    if udt_type in self.built_in_types:
      return PostgresTypeToLogicaType(udt_type)

    if udt_type in self.name_to_type_cache:
      return self.name_to_type_cache[udt_type]

    return None

  def UnpackTypes(self, types: [str], conn) -> Dict[str, str]:
    result = {type: self.UnpackTypeByCachesOnly(type) for type in types}
    not_cached_types = [udt_type.lstrip('_') for udt_type, type in result.items() if not type]
    self.PopulateCacheByTypes(not_cached_types, conn)

    for udt_type, type in result.items():
      if not type:
        result[udt_type] = self.UnpackTypeByCachesOnly(udt_type)

    return result
  
  def PopulateCacheByTypes(self, types: [str], conn):
    if not types:
      return

    with conn.cursor() as cur:
      # this SQL query returns all nested types used in definition of given udt_type
      cur.execute('''
WITH RECURSIVE R AS (SELECT pg_attribute.attname AS field_name,
                            child_type.typname   AS field_type,
                            parent_type.typname  AS parent_type
                     FROM pg_type AS parent_type
                              JOIN pg_attribute ON pg_attribute.attrelid = parent_type.typrelid
                              JOIN pg_type AS child_type ON child_type.oid = pg_attribute.atttypid
                     WHERE parent_type.typname IN %s

                     UNION

                     SELECT pg_attribute.attname                AS field_name,
                            child_type.typname                  AS field_type,
                            trim(leading '_' from R.field_type) AS parent_type
                     FROM pg_type AS parent_type
                              JOIN R ON parent_type.typname = trim(leading '_' from R.field_type)
                              JOIN pg_attribute ON pg_attribute.attrelid = parent_type.typrelid
                              JOIN pg_type AS child_type ON child_type.oid = pg_attribute.atttypid)
SELECT parent_type, jsonb_object_agg(field_name, field_type)
FROM R
GROUP BY parent_type;''', (tuple(types),))

      new_types = {type_name: fields for type_name, fields in cur.fetchall()}
      self.AdjustNestedTypes(new_types, conn)

  def AdjustNestedTypes(self, new_types: Dict[str, Dict[str, str]], conn):
    while new_types:
      keys_to_delete = []

      for type_name, fields in new_types.items():
        if all(type.lstrip('_') not in new_types for type in fields.values()):
          fields = (f'{field_name}: {self.UnpackTypeByCachesOnly(field_type)}' for field_name, field_type in fields.items())
          self.name_to_type_cache[type_name] = f'{{{", ".join(fields)}}}'
          keys_to_delete.append(type_name)

      for key_to_delete in keys_to_delete:
        del new_types[key_to_delete]
