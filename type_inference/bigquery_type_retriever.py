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

import re

if '.' not in __package__:
  from type_inference import bigquery_type_parser
else:
  from ..type_inference import bigquery_type_parser


class BigQueryTypeRetriever:
  """For all given types builds its string representation as composition of Logica's primitive types."""
  def __init__(self):
    self.array_regexp = re.compile(r'ARRAY<(.*)>')
    self.struct_regexp = re.compile(r'STRUCT<(.*)>')
    self.name_to_type_cache = dict()

  def UnpackTypeWithCaching(self, type: str) -> str:
    if type not in self.name_to_type_cache:
      self.name_to_type_cache[type] = self.UnpackType(type)

    return self.name_to_type_cache[type]

  def UnpackType(self, type: str) -> str:
    def ParseBigQueryStruct(type):
      nesting_level = 0
      start_index = 0
      fields = {}
      field_name = ''

      for index, char in enumerate(type):
        if char == '<':
          nesting_level += 1
        elif char == '>':
          nesting_level -= 1
        elif nesting_level == 0:
          if char == ' ':
            field_name = type[start_index:index].lstrip()
            start_index = index + 1
          elif char == ',':
            fields[field_name] = type[start_index:index].lstrip()
            start_index = index + 1

      fields[field_name] = type[start_index:].lstrip()
      return fields

    result = bigquery_type_parser.BigQueryTypeToLogicaType(type)

    if result:
      return result

    array_match = self.array_regexp.match(type)

    if array_match:
      return '[%s]' % self.UnpackTypeWithCaching(array_match.group(1))

    struct_match = self.struct_regexp.match(type)
    
    if struct_match:
      fields = ParseBigQueryStruct(struct_match.group(1))
      fields = (f'{field_name}: {self.UnpackTypeWithCaching(field_type)}' for field_name, field_type in fields.items())
      return '{%s}' % (', '.join(fields))

    assert False, 'Unknown BigQuery type! %s' % type