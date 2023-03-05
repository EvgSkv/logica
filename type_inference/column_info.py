class ColumnInfo:
  def __init__(self, column_name: str, table_name: str, type_name: str):
    self.column_name = column_name
    self.table_name = table_name
    self.type_name = type_name

  def __str__(self):
    return f'{self.table_name} - {self.column_name} - {self.type_name}'
