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

import abc


class TypeRetrieverBase(abc.ABC):
  """For all given types builds its string representation as composition of Logica's primitive types."""
  def __init__(self):
    self.name_to_type_cache = dict()

  def UnpackTypeWithCaching(self, type: str) -> str:
    if type not in self.name_to_type_cache:
      self.name_to_type_cache[type] = self.UnpackType(type)

    return self.name_to_type_cache[type]

  @abc.abstractmethod
  def UnpackType(self, type: str) -> str:
    """Returns string representation of the given type"""
