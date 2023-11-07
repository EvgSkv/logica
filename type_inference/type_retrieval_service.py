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
from type_inference.type_retrieval_exception import TypeRetrievalException
from type_inference.built_in_type_retriever import BuiltInTypeRetriever
import psycopg2

def ValidateRuleAndGetTableName(rule: dict) -> str:
  rule_text = rule['full_text']
  field_value = rule['head']['record']['field_value']

  if len(field_value) != 1 or field_value[0]['field'] != '*':
    raise TypeRetrievalException(rule_text)

  conjuncts = rule['body']['conjunction']['conjunct']

  if len(conjuncts) != 1:
    raise TypeRetrievalException(rule_text)

  conjunct = conjuncts[0]

  if 'predicate' not in conjunct:
    raise TypeRetrievalException(rule_text)

  field_values = conjunct['predicate']['record']['field_value']

  if len(field_values) != 1 or field_values[0]['field'] != '*':
    raise TypeRetrievalException(rule_text)

  return conjuncts[0]['predicate']['predicate_name'].split('.')[1]  # TODO: Validate schema of the called table.


class TypeRetrievalService:
  def __init__(self, parsed_rules, predicate_names,
               connection_string='dbname=logica user=logica password=logica host=127.0.0.1'):
    predicate_names_as_set = set(predicate_names)
    self.parsed_rules = [r for r in parsed_rules if r['head']['predicate_name'] in predicate_names_as_set]
    self.connection_string = connection_string
    self.table_names = self.ValidateParsedRulesAndGetTableNames()
    self.built_inTypes_retriever = BuiltInTypeRetriever()
    self.built_inTypes_retriever.InitBuiltInTypes(self.connection_string)

  def ValidateParsedRulesAndGetTableNames(self) -> Dict[str, str]:
    return {rule['head']['predicate_name']: ValidateRuleAndGetTableName(rule) for rule in self.parsed_rules}

  def RetrieveTypes(self, filename='default.l'):
    filename = filename.replace('.l', '_schema.l')
    with psycopg2.connect(self.connection_string) as conn:
      with conn.cursor() as cursor:
        # for each given table this SQL query returns json object
        # where keys are names of columns in that table and values are corresponding types
        cursor.execute('''
SELECT table_name, jsonb_object_agg(column_name, udt_name)
FROM information_schema.columns
GROUP BY table_name
HAVING table_name IN %s;''', (self.table_names.values(),))
        columns = {table: columns for table, columns in cursor.fetchall()}

      result = []

      for rule in self.parsed_rules:
        result.append(f'{rule["full_text"]},')
        local = []

        for column, udt_type in sorted(columns[self.table_names[rule['head']['predicate_name']]].items(), key=lambda t: t[0]):
          local.append(f'{column}: {UnpackType(udt_type, conn)}')

        var_name = rule['head']['record']['field_value'][0]['value']['expression']['variable']['var_name']
        fields = ", ".join(local)
        result.append('%s ~ {%s};\n' % (var_name, fields))

      with open(filename, 'w') as writefile:
        writefile.writelines('\n'.join(result))
