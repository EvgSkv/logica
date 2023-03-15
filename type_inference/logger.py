class Logger:
  def __init__(self):
    self._not_found_tables = []
  def not_found_table(self, table_name: str):
    self._not_found_tables.append(table_name)
