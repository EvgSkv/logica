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

if '.' not in __package__:
  from type_inference import type_retrieval_service_base
else:
  from ..type_inference import type_retrieval_service_base


class PostgresqlTypeRetrievalService(
  type_retrieval_service_base.TypeRetrievalServiceBase):
  """The class is an entry point for type retrieval using postgresql."""
  def __init__(self, parsed_rules, predicate_names,
               connection_string='dbname=logica user=logica password=logica host=127.0.0.1'):
    if '.' not in __package__:
        from type_inference import psql_type_retriever
    else:
        from . import psql_type_retriever
    psql_type_retriever = psql_type_retriever.PostgresqlTypeRetriever()
    super().__init__(parsed_rules, predicate_names, psql_type_retriever, lower_table_name=True)
    self.connection_string = connection_string
    psql_type_retriever.ExtractTypeInfo(self.connection_string)

  def GetColumns(self):
    import psycopg2
    with psycopg2.connect(self.connection_string) as conn:
      with conn.cursor() as cursor:
        cursor.execute('''
SELECT table_name, jsonb_object_agg(column_name, udt_name)
FROM information_schema.columns
GROUP BY table_name
HAVING table_name IN %s;''', (tuple(self.table_names.values()),))
        return {table: columns for table, columns in cursor.fetchall()}
