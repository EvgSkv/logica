#!/usr/bin/python
#
# Copyright 2023 Google LLC
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

if '.' not in __package__:
  from type_inference.research import reference_algebra
else:
  from ..research import reference_algebra
  
def TypesOfBultins():
    x = reference_algebra.TypeReference('Any')
    y = reference_algebra.TypeReference('Any')
    list_of_x = reference_algebra.TypeReference('Any')
    reference_algebra.UnifyListElement(list_of_x, x)

    types_of_predicate = {
        '=': {
          'left': x,
          'right': x,
          'logica_value': x
        },
        '++': {
          'left': 'Str',
          'right': 'Str',
          'logica_value': 'Str' 
        },
        '+': {
            'left': 'Num',
            'right': 'Num',
            'logica_value': 'Num'
        },
        '*': {
            'left': 'Num',
            'right': 'Num',
            'logica_value': 'Num'
        },
        '^': {
            'left': 'Num',
            'right': 'Num',
            'logica_value': 'Num'
        }, 
        'Num': {
            0: 'Num',
            'logica_value': 'Num'
        },
        'Str': {
            0: 'Str',
            'logica_value': 'Str'
        },
        'Agg+': {
            0: 'Num',
            'logica_value': 'Num'
        },
        'List': {
            0: x,
            'logica_value': list_of_x
        },
        '->': {
           'left': x,
           'right': y,
           'logica_value': reference_algebra.ClosedRecord({'arg': x, 'value': y})
        },
        'ArgMin': {
           0: reference_algebra.ClosedRecord({'arg': x, 'value': y}),
           'logica_value': x
        }
    }
    return {
        p: {k: reference_algebra.TypeReference(v)
            for k, v in types.items()}
        for p, types in types_of_predicate.items()
    }
