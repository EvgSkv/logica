from logging import error
from common import color


class TableNotExistException(Exception):
  def __init__(self, table_name: str):
    error(color.Format('{underline}Database engine{end}:'))
    error(f'{color.Format("[ {error}Error{end} ]")} table [{table_name}] doesn\'t exist')