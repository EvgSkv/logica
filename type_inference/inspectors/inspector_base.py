from typing import Dict

from type_inference.types.variable_types import Type


class Inspector:
  def TryGetColumnsInfo(self, table_name: str) -> Dict[str, Type]:
    pass
