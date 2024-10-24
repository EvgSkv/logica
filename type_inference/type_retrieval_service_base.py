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

import abc
from typing import Dict

if '.' not in __package__:
  from type_inference import bad_schema_exception
else:
  from ..type_inference import bad_schema_exception


def ValidateRuleAndGetTableName(rule: dict, lower_table_name: bool = False) -> str:
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

  predicate_name = conjuncts[0]['predicate']['predicate_name'].split('.')[1]  # TODO: Validate schema of the called table.
  return predicate_name.lower() if lower_table_name else predicate_name


class TypeRetrievalServiceBase(abc.ABC):
  """The class is an abstract base class for specific engine type retrieval services."""
  def __init__(self, parsed_rules, predicate_names, type_retriever, lower_table_name=False):
    predicate_names_as_set = set(predicate_names)
    self.parsed_rules = [r for r in parsed_rules 
                         if r['head']['predicate_name'] in predicate_names_as_set]
    self.table_names = self.ValidateParsedRulesAndGetTableNames(lower_table_name)
    self.type_retriever = type_retriever

  def ValidateParsedRulesAndGetTableNames(self, lower_table_name) -> Dict[str, str]:
    return {rule['head']['predicate_name']: ValidateRuleAndGetTableName(rule, lower_table_name) 
            for rule in self.parsed_rules}

  def RetrieveTypes(self, filename):
    filename = filename.replace('.l', '_schema.l')

    columns = self.GetColumns()

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

  @abc.abstractmethod
  def GetColumns(self):
    """
    For each table this method returns json object 
    where keys are names of columns in that table and values are corresponding types
    """
