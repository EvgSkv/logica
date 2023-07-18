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

from collections import defaultdict
from typing import Tuple

from type_inference.type_inference_exception import TypeInferenceException
from type_inference.types.variable_types import ListType, NumberType, StringType, AtomicType, BoolType

built_in_restrictions = defaultdict(dict)
number_type = NumberType()
string_type = StringType()
atomic_type = AtomicType()
bool_type = BoolType()

built_in_restrictions['Range']['col0'] = number_type
built_in_restrictions['Range']['logica_value'] = ListType(number_type)

built_in_restrictions['Num']['col0'] = number_type
built_in_restrictions['Num']['logica_value'] = number_type

built_in_restrictions['Str']['col0'] = string_type
built_in_restrictions['Str']['logica_value'] = string_type

built_in_restrictions['+']['left'] = number_type
built_in_restrictions['+']['right'] = number_type
built_in_restrictions['+']['logica_value'] = number_type

built_in_restrictions['++']['left'] = string_type
built_in_restrictions['++']['right'] = string_type
built_in_restrictions['++']['logica_value'] = string_type

built_in_restrictions['<']['left'] = atomic_type
built_in_restrictions['<']['right'] = atomic_type
built_in_restrictions['<']['logica_value'] = bool_type

built_in_restrictions['>']['left'] = atomic_type
built_in_restrictions['>']['right'] = atomic_type
built_in_restrictions['>']['logica_value'] = bool_type

built_in_restrictions['<=']['left'] = atomic_type
built_in_restrictions['<=']['right'] = atomic_type
built_in_restrictions['<=']['logica_value'] = bool_type

built_in_restrictions['>=']['left'] = atomic_type
built_in_restrictions['>=']['right'] = atomic_type
built_in_restrictions['>=']['logica_value'] = bool_type


def CheckInequalities(args: dict, bounds: Tuple[int, int], ):
  args_types_set = {args['left'], args['right']}

  if args_types_set == {number_type} or args_types_set == {atomic_type, number_type}:
    return {'left': number_type, 'right': number_type}
  elif args_types_set == {string_type} or args_types_set == {atomic_type, string_type}:
    return {'left': string_type, 'right': string_type}
  elif args_types_set == {atomic_type}:
    return {'left': atomic_type, 'right': atomic_type}

  raise TypeInferenceException(args['left'].type, args['right'].type, bounds)


built_in_concrete_types = {'<': CheckInequalities,
                           '>': CheckInequalities,
                           '<=': CheckInequalities,
                           '>=': CheckInequalities}
