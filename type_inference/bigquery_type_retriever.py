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

from google.colab import bigquery

if '.' not in __package__:
  from type_inference import bigquery_type_parser
else:
  import bigquery_type_parser


class BigQueryTypeRetriever:
  """For all given types builds its string representation as composition of Logica's primitive types."""
  def __init__(self):
    self.built_in_types = set()
    self.user_defined_types = dict()
    self.name_to_type_cache = dict()

  def ExtractTypeInfo(self, credentials: str, project: str):
    if self.built_in_types and self.user_defined_types:
      return

    client = bigquery.Client(credentials=credentials, project=project)
    # this SQL query takes all types and returns them
    # with boolean flag "is that type built in" and
    # JSON array of its fields (null for primitive types)
    types_info = client.query().to_dataframe() # todo query

    for type, is_built_in, fields in types_info:
        if is_built_in:
            self.built_in_types.add(type)
        else:
            self.user_defined_types[type] = {field['field_name']: field['field_type'] for field in fields} if fields else {}

  def UnpackTypeWithCaching(self, type: str) -> str:
    if type not in self.name_to_type_cache:
      self.name_to_type_cache[type] = self.UnpackType(type)

    return self.name_to_type_cache[type]
  
  def UnpackType(self, type: str) -> str:
    if type.startswith('_'):
      return '[%s]' % self.UnpackTypeWithCaching(type[1:])
    
    if type in self.built_in_types:
      return bigquery_type_parser.BigQueryTypeToLogicaType(type)
    
    fields = self.user_defined_types[type]
    fields = (f'{field_name}: {self.UnpackTypeWithCaching(field_type)}' for field_name, field_type in fields.items())
    return '{%s}' % (', '.join(fields))


