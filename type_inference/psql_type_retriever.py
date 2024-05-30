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

import psycopg2

if '.' not in __package__:
  from type_inference import type_retriever_base, psql_type_parser
else:
  from ..type_inference import type_retriever_base, psql_type_parser


class PostgresqlTypeRetriever(type_retriever_base.TypeRetrieverBase):
  def __init__(self):
    super().__init__()
    self.built_in_types = set()
    self.user_defined_types = dict()

  def ExtractTypeInfo(self, connection_string: str):
    if self.built_in_types and self.user_defined_types:
      return

    with psycopg2.connect(connection_string) as conn:
      with conn.cursor() as cur:
        # this SQL query takes all types and returns them
        # with boolean flag "is that type built in" and
        # JSON array of its fields (null for primitive types)
        cur.execute('''
SELECT t.typname                AS type,
       n.nspname = 'pg_catalog' AS is_built_in,
       CASE
           WHEN bool_and(pg_attribute.attname IS NULL) THEN NULL
           ELSE jsonb_agg(json_build_object('field_name', pg_attribute.attname, 'field_type', child_type.typname)) END
                                AS fields
FROM pg_type t
         LEFT JOIN pg_attribute ON pg_attribute.attrelid = t.typrelid
         LEFT JOIN pg_type AS child_type ON child_type.oid = pg_attribute.atttypid
         JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
WHERE n.nspname <> 'information_schema'
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
    )
GROUP BY t.typname, n.nspname;''')

        for type, is_built_in, fields in cur.fetchall():
          if is_built_in:
            self.built_in_types.add(type)
          else:
            self.user_defined_types[type] = {field['field_name']: field['field_type'] for field in fields} if fields else {}
  
  def UnpackType(self, type: str) -> str:
    if type.startswith('_'):
      return '[%s]' % self.UnpackTypeWithCaching(type[1:])
    
    if type in self.built_in_types:
      return psql_type_parser.PostgresTypeToLogicaType(type)
    
    fields = self.user_defined_types[type]
    fields = (f'{field_name}: {self.UnpackTypeWithCaching(field_type)}' for field_name, field_type in fields.items())
    return '{%s}' % (', '.join(fields))
