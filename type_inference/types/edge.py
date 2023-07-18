#!/usr/bin/python
#
# Copyright 2023 Logica Authors
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

from typing import Tuple

from type_inference.types.expression import Expression, SubscriptAddressing, PredicateAddressing


class Edge:
  def __init__(self, vertices: Tuple[Expression, Expression], bounds: Tuple[int, int]):
    self.vertices = vertices
    self.bounds = bounds

  def __eq__(self, other):
    return isinstance(other, type(self)) and (set(self.vertices), self.bounds) == (set(other.vertices), other.bounds)

  def __hash__(self):
    return hash((frozenset(self.vertices), self.bounds))


class Equality(Edge):
  def __init__(self, left: Expression, right: Expression, bounds: Tuple[int, int]):
    super().__init__((left, right), bounds)
    self.left = left
    self.right = right


class EqualityOfElement(Edge):
  def __init__(self, list: Expression, element: Expression, bounds: Tuple[int, int]):
    super().__init__((list, element), bounds)
    self.list = list
    self.element = element


class FieldBelonging(Edge):
  def __init__(self, parent: Expression, field: SubscriptAddressing, bounds: Tuple[int, int]):
    super().__init__((parent, field), bounds)
    self.parent = parent
    self.field = field


class PredicateArgument(Edge):
  def __init__(self, logica_value: PredicateAddressing, argument: PredicateAddressing, bounds: Tuple[int, int]):
    super().__init__((logica_value, argument), bounds)
    self.logica_value = logica_value
    self.argument = argument
