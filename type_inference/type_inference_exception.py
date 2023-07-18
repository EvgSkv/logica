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

from logging import error
from typing import Tuple

from common import color
from type_inference.types.variable_types import Type


class TypeInferenceException(Exception):
  def __init__(self, left: Type, right: Type, bounds: Tuple[int, int]):
    self.bounds = bounds
    error(color.Format('{underline}Infering types{end}:'))
    error(f'{color.Format("[ {error}Error{end} ]")} can\'t match {left} with {right} at ({bounds[0]};{bounds[1]})\n')
