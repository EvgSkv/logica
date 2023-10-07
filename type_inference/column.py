class Column:
  def __init__(self, column_name: str, data_type: str, udt_name: str):
    self.udt_name = udt_name
    self.data_type = data_type
    self.column_name = column_name