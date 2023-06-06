from type_inference.types.variable_types import Type


class ColumnInfo:
  def __init__(self, column_name: str, table_name: str, type: Type):
    self.column_name = column_name
    self.table_name = table_name
    self.type = type

  def __str__(self):
    return f'{self.table_name} - {self.column_name} - {self.type}'
