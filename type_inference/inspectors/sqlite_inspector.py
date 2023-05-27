import sqlite3
from typing import List

from type_inference.column_info import ColumnInfo
from type_inference.inspectors.inspector_base import Inspector
from type_inference.logger import Logger


class SQLiteInspector(Inspector):
  def __init__(self, db_file: str, logger: Logger):
    self._logger = logger
    self._conn = sqlite3.connect(db_file)

  def try_get_columns_info(self, table_name: str) -> List[ColumnInfo]:
    with self._conn.cursor() as cursor:
      table_exists = cursor.execute(
        f''' SELECT name FROM sqlite_master 
        WHERE type='table' AND name="{table_name}" ''').fetchall()

      if not table_exists:
        self._logger.not_found_table(table_name)
        return []

      columns_info = cursor.execute(
        f'PRAGMA table_info({table_name});').fetchall()
      return [ColumnInfo(column_name=column[1], table_name=table_name, type_name=column[2])
              for column in columns_info]
