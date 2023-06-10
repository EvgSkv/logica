import sqlite3
from typing import Dict

from type_inference.inspectors.inspector_base import Inspector
from type_inference.logger import Logger
from type_inference.types.variable_types import AnyType, NumberType, StringType, Type


def convert(sqlite_type: str) -> Type:
  lower_sqlite_type = sqlite_type.lower()
  if lower_sqlite_type == 'null':
    return AnyType()  # todo nulltype
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
    return {column[1]: convert(column[2]) for column in columns_info}
