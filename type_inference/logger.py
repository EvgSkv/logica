#!/usr/bin/python
#
# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from type_inference.types.edge import Edge
from type_inference.types.variable_types import Type


class Logger:
  def __init__(self):
    self._not_found_tables = []
    self._edges = []

  def NotFoundTable(self, table_name: str):
    self._not_found_tables.append(table_name)

  def TypesNotMatch(self, edge: Edge, left_type: Type, right_type: Type):
    self._edges.append((edge, left_type, right_type))
