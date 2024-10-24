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

from type_inference import bq_type_parser

from . import bq_type_parser

if '.' not in __package__:
  from type_inference import type_retriever_base
  from type_inference import unknown_bigquery_type_exception
else:
  from ..type_inference import type_retriever_base
  from ..type_inference import unknown_bigquery_type_exception


class BigQueryTypeRetriever(type_retriever_base.TypeRetrieverBase):
  def __init__(self):
    super().__init__()
    self.array_regexp = re.compile(r'ARRAY<(.*)>')
    self.struct_regexp = re.compile(r'STRUCT<(.*)>')

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

    result = bq_type_parser.BigQueryTypeToLogicaType(type)

    if result:
      return result

    array_match = self.array_regexp.match(type)

    if array_match:
      return '[%s]' % self.UnpackTypeWithCaching(array_match.group(1))

    struct_match = self.struct_regexp.match(type)

    if struct_match:
      fields_dict = ParseBigQueryStruct(struct_match.group(1))
      fields = (f'{field_name}: {self.UnpackTypeWithCaching(field_type)}'
                for field_name, field_type in fields_dict.items())
      return '{%s}' % (', '.join(fields))

    raise unknown_bigquery_type_exception.UnknownBigQueryTypeException(type)
