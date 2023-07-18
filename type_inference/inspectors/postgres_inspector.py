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

from sqlalchemy import create_engine, inspect, types

from type_inference.inspectors.inspector_base import Inspector
from type_inference.inspectors.table_not_exist_exception import TableDoesNotExistException
from type_inference.types.variable_types import Type, NumberType, ListType, StringType, RecordType


def Convert(postgres_type: types) -> Type:
  if postgres_type.python_type == int:
    return NumberType()
  if postgres_type.python_type == str:
    return StringType()
  if postgres_type.python_type == bool:
    raise NotImplementedError()
  if postgres_type.python_type == list:
    return ListType(Convert(postgres_type.item_type))
  if postgres_type.python_type == dict:
    return RecordType({}, False)
  raise NotImplementedError()


class PostgresInspector(Inspector):
  def __init__(self, username: str, password: str, host: str = '127.0.0.1'):
    engine = create_engine(
      f'postgresql+psycopg2://{username}:{password}@{host}', pool_recycle=3600, pool_pre_ping=True)
    self._inspector = inspect(engine)

  def TryGetColumnsInfo(self, table_name: str) -> Dict[str, Type]:
    if not self._inspector.has_table(table_name):
      raise TableDoesNotExistException(table_name)
    columns_info = self._inspector.get_columns(table_name)
    return {column['name']: Convert(column['type']) for column in columns_info}
