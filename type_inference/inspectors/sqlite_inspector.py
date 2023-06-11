#!/usr/bin/python
#
# Copyright 2023 Logica
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

import sqlite3
from typing import Dict

from type_inference.inspectors.inspector_base import Inspector
from type_inference.logger import Logger
from type_inference.types.variable_types import NumberType, StringType, Type


def Convert(sqlite_type: str) -> Type:
  lower_sqlite_type = sqlite_type.lower()
  if lower_sqlite_type == 'null':
    raise NotImplementedError()
  if lower_sqlite_type == 'integer' or lower_sqlite_type == 'real':
    return NumberType()
  if lower_sqlite_type == 'text':
    return StringType()
  raise NotImplementedError(sqlite_type)


class SQLiteInspector(Inspector):
  def __init__(self, db_path: str, logger: Logger):
    self._logger = logger
    self.db_path = db_path

  def TryGetColumnsInfo(self, table_name: str) -> Dict[str, Type]:
    with sqlite3.connect(self.db_path) as conn:
      cursor = conn.cursor()
      columns_info = cursor.execute(f'PRAGMA table_info({table_name});').fetchall()
    return {column[1]: Convert(column[2]) for column in columns_info}
