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
import psycopg2
from google.colab import bigquery

if '.' not in __package__:
  from common import color
  from type_inference import bad_schema_exception
  from type_inference import postgresql_type_retriever
  from type_inference import bigquery_type_retriever
else:
  import bad_schema_exception
  import postgresql_type_retriever
  import bigquery_type_retriever


def ValidateRuleAndGetTableName(rule: dict) -> str:
  rule_text = rule['full_text']
  field_value = rule['head']['record']['field_value']

  if len(field_value) != 1 or field_value[0]['field'] != '*':
    raise bad_schema_exception.BadSchemaException(rule_text)

  conjuncts = rule['body']['conjunction']['conjunct']

  if len(conjuncts) != 1:
    raise bad_schema_exception.BadSchemaException(rule_text)

  conjunct = conjuncts[0]

  if 'predicate' not in conjunct:
    raise bad_schema_exception.BadSchemaException(rule_text)

  field_values = conjunct['predicate']['record']['field_value']

  if len(field_values) != 1 or field_values[0]['field'] != '*':
    raise bad_schema_exception.BadSchemaException(rule_text)

  return conjuncts[0]['predicate']['predicate_name'].split('.')[1].lower()  # TODO: Validate schema of the called table.


class PostgresqlTypeRetrievalService:
  """The class is an entry point for type retrieval using postgresql."""
  def __init__(self, parsed_rules, predicate_names,
               connection_string='dbname=logica user=logica password=logica host=127.0.0.1'):
    predicate_names_as_set = set(predicate_names)
    self.parsed_rules = [r for r in parsed_rules if r['head']['predicate_name'] in predicate_names_as_set]
    self.connection_string = connection_string
    self.table_names = self.ValidateParsedRulesAndGetTableNames()
    self.type_retriever = postgresql_type_retriever.PostgresqlTypeRetriever()
    self.type_retriever.ExtractTypeInfo(self.connection_string)

  def ValidateParsedRulesAndGetTableNames(self) -> Dict[str, str]:
    return {rule['head']['predicate_name']: ValidateRuleAndGetTableName(rule) for rule in self.parsed_rules}

  def RetrieveTypes(self, filename):
    filename = filename.replace('.l', '_schema.l')

    with psycopg2.connect(self.connection_string) as conn:
      with conn.cursor() as cursor:
        # for each given table this SQL query returns json object
        # where keys are names of columns in that table and values are corresponding types
        cursor.execute('''
SELECT table_name, jsonb_object_agg(column_name, udt_name)
FROM information_schema.columns
GROUP BY table_name
HAVING table_name IN %s;''', (tuple(self.table_names.values()),))
        columns = {table: columns for table, columns in cursor.fetchall()}

      resulting_rule_lines = []

      for rule in self.parsed_rules:
        resulting_rule_lines.append(f'{rule["full_text"]},')
        table_columns = columns[self.table_names[rule['head']['predicate_name']]]
        fields = (f'{column}: {self.type_retriever.UnpackTypeWithCaching(udt_type)}' for column, udt_type in sorted(table_columns.items()))

        var_name = rule['head']['record']['field_value'][0]['value']['expression']['variable']['var_name']
        fields_line = ', '.join(fields)
        resulting_rule_lines.append('  %s ~ {%s};\n' % (var_name, fields_line))

      with open(filename, 'w') as file:
        file.writelines('\n'.join(resulting_rule_lines))


class BigQueryTypeRetrievalService:
  """The class is an entry point for type retrieval using bigquery."""
  def __init__(self, parsed_rules, predicate_names,
               credentials='', project=''):
    predicate_names_as_set = set(predicate_names)
    self.parsed_rules = [r for r in parsed_rules if r['head']['predicate_name'] in predicate_names_as_set]
    self.credentials = credentials
    self.project = project
    self.table_names = self.ValidateParsedRulesAndGetTableNames()
    self.type_retriever = bigquery_type_retriever.BigQueryTypeRetriever()
    self.type_retriever.ExtractTypeInfo(self.connection_string)

  def ValidateParsedRulesAndGetTableNames(self) -> Dict[str, str]:
    return {rule['head']['predicate_name']: ValidateRuleAndGetTableName(rule) for rule in self.parsed_rules}

  def RetrieveTypes(self, filename):
    filename = filename.replace('.l', '_schema.l')

    client = bigquery.Client(credentials=self.credentials, project=self.project)
    result = client.query() # todo query
        # for each given table this SQL query returns json object
        # where keys are names of columns in that table and values are corresponding types
    columns = {table: columns for table, columns in result.to_dataframe()}

    resulting_rule_lines = []

    for rule in self.parsed_rules:
      resulting_rule_lines.append(f'{rule["full_text"]},')
      table_columns = columns[self.table_names[rule['head']['predicate_name']]]
      fields = (f'{column}: {self.type_retriever.UnpackTypeWithCaching(udt_type)}' for column, udt_type in sorted(table_columns.items()))

      var_name = rule['head']['record']['field_value'][0]['value']['expression']['variable']['var_name']
      fields_line = ', '.join(fields)
      resulting_rule_lines.append('  %s ~ {%s};\n' % (var_name, fields_line))

    with open(filename, 'w') as file:
      file.writelines('\n'.join(resulting_rule_lines))
