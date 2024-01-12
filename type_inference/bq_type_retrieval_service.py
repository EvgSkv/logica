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

import json

if '.' not in __package__:
  from type_inference import type_retrieval_service_base
else:
  from ..type_inference import type_retrieval_service_base


class BigQueryTypeRetrievalService(
  type_retrieval_service_base.TypeRetrievalServiceBase):
  """The class is an entry point for type retrieval using bigquery."""
  def __init__(self, parsed_rules, predicate_names,
               credentials=None, project='bigquery-logica'):
    if '.' not in __package__:
      from type_inference import bq_type_retriever
    else:
      from . import bq_type_retriever
    bq_type_retriever = bq_type_retriever.BigQueryTypeRetriever()
    super().__init__(parsed_rules, predicate_names, bq_type_retriever)
    self.project = project
    self.credentials = credentials

  def GetColumns(self):
    from google.cloud import bigquery

    # it works for us even if we don't give any credentials
    client = bigquery.Client(credentials=self.credentials, 
                             project=self.project) 
    job_config = bigquery.QueryJobConfig(
      query_parameters=[
        bigquery.ArrayQueryParameter("tables", "STRING", self.table_names),
      ]
    )
    query = client.query('''
SELECT table_name, JSON_OBJECT(ARRAY_AGG(column_name), ARRAY_AGG(data_type)) 
                   AS columns
FROM logica_test.INFORMATION_SCHEMA.COLUMNS
GROUP BY table_name
HAVING table_name IN UNNEST(@tables);''', job_config)
    data_by_table_name = query.to_dataframe().set_index('table_name')
    columns_by_table_name = data_by_table_name.to_dict()['columns'].items()
    return {table: json.loads(type)
               for table, type in columns_by_table_name}
