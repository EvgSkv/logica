from collections import defaultdict


class TypesGraph:
  def __init__(self):
    self.variable_connections = defaultdict(lambda: defaultdict(lambda: []))

  def connect(self, first_variable: str, second_variable: str, context):
    self.variable_connections[first_variable][second_variable].append(context)
    self.variable_connections[second_variable][first_variable].append(context)
