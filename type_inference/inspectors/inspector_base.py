from typing import Dict

from type_inference.types.variable_types import Type


class Inspector:
  def try_get_columns_info(self, table_name: str) -> Dict[str, Type]:
    pass
