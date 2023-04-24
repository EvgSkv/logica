from typing import List

from sqlalchemy import create_engine, inspect

from type_inference.column_info import ColumnInfo
from type_inference.inspectors.inspector_base import Inspector
from type_inference.logger import Logger


class PostgresInspector(Inspector):
  def __init__(self, username: str, password: str, logger: Logger, host: str = '127.0.0.1'):
    self._logger = logger
    engine = create_engine(
      f'postgresql+psycopg2://{username}:{password}@{host}', pool_recycle=3600)
    self._inspector = inspect(engine)

  def try_get_columns_info(self, table_name: str) -> List[ColumnInfo]:
    if not self._inspector.has_table(table_name):
      self._logger.not_found_table(table_name)
      return []
    columns_info = self._inspector.get_columns(table_name)
    return [ColumnInfo(column['name'], table_name, column['type'])
            for column in columns_info]
