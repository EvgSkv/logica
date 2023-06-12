#!/usr/bin/python
#
# Copyright 2023 Logica
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

from type_inference.types.variable_types import ListType, NumberType, StringType, AtomicType, BoolType

built_in = defaultdict(dict)
number_type = NumberType()
string_type = StringType()
atomic_type = AtomicType()
bool_type = BoolType()

built_in['Range']['col0'] = number_type
built_in['Range']['logica_value'] = ListType(number_type)

built_in['Num']['col0'] = number_type
built_in['Num']['logica_value'] = number_type

built_in['Str']['col0'] = string_type
built_in['Str']['logica_value'] = string_type

built_in['+']['left'] = number_type
built_in['+']['right'] = number_type
built_in['+']['logica_value'] = number_type

built_in['++']['left'] = string_type
built_in['++']['right'] = string_type
built_in['++']['logica_value'] = string_type

built_in['<']['left'] = atomic_type
built_in['<']['right'] = atomic_type
built_in['<']['logica_value'] = bool_type

built_in['>']['left'] = atomic_type
built_in['>']['right'] = atomic_type
built_in['>']['logica_value'] = bool_type

built_in['<=']['left'] = atomic_type
built_in['<=']['right'] = atomic_type
built_in['<=']['logica_value'] = bool_type

built_in['>=']['left'] = atomic_type
built_in['>=']['right'] = atomic_type
built_in['>=']['logica_value'] = bool_type
