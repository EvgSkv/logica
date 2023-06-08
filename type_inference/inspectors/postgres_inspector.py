from typing import Dict

from sqlalchemy import create_engine, inspect, types

from type_inference.types.variable_types import Type, NumberType, ListType, StringType, RecordType, AnyType
from type_inference.inspectors.inspector_base import Inspector
from type_inference.logger import Logger


def convert(postgres_type: types) -> Type:
  if postgres_type.python_type == int:
    return NumberType()
  if postgres_type.python_type == str:
    return StringType()
  if postgres_type.python_type == bool:
    raise NotImplementedError()
  if postgres_type.python_type == list:
    return ListType(convert(postgres_type.item_type))
  if postgres_type.python_type == dict:
    return RecordType({}, False)
  raise NotImplementedError()



class PostgresInspector(Inspector):
  def __init__(self, username: str, password: str, logger: Logger, host: str = '127.0.0.1'):
    self._logger = logger
    engine = create_engine(
      f'postgresql+psycopg2://{username}:{password}@{host}', pool_recycle=3600)
    self._inspector = inspect(engine)

  def try_get_columns_info(self, table_name: str) -> Dict[str, Type]:
    columns_info = self._inspector.get_columns(table_name)
    return {column['name']: convert(column['type']) for column in columns_info}
