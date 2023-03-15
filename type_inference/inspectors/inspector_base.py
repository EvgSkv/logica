from typing import List

from type_inference.column_info import ColumnInfo


class Inspector:
  def try_get_columns_info(self, table_name: str) -> List[ColumnInfo]:
    pass
