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
    # Special X that ends up singular in SQLite.
    special_x = reference_algebra.TypeReference('Any')
    list_of_e = reference_algebra.TypeReference('Any')
    e = reference_algebra.TypeReference('Singular')
    reference_algebra.UnifyListElement(list_of_e, e)
    sequential = reference_algebra.TypeReference('Sequential')

    types_of_predicate = {
        'Aggr': {
            0: x,
            'logica_value': x
        },
        '==': {
           'left': x,
           'right': x,
           'logica_value': 'Bool'
        },
        '=': {
          'left': x,
          'right': x,
          'logica_value': x
        },
        '~': {
          'left': x,
          'right': x,
          'logica_value': 'Bool'
        },
        '++': {
          'left': sequential,
          'right': sequential,
          'logica_value': sequential 
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
        'Time': {
            'logica_value': 'Time'
        },
        'Agg+': {
            0: 'Num',
            'logica_value': 'Num'
        },
        'List': {
            0: e,
            'logica_value': list_of_e
        },
        'Set': {
            0: e,
            'logica_value': list_of_e 
        },
        '->': {
           'left': x,
           'right': y,
           'logica_value': reference_algebra.ClosedRecord({'arg': x, 'value': y})
        },
        'ArgMin': {
           0: reference_algebra.ClosedRecord({'arg': special_x, 'value': y}),
           'logica_value': special_x
        },
        'ArgMax': {
           0: reference_algebra.ClosedRecord({'arg': special_x, 'value': y}),
           'logica_value': special_x
        },
        'ArgMinK': {
           0: reference_algebra.ClosedRecord({'arg': e, 'value': y}),
           1: 'Num',
           'logica_value': [e]
        },
        'ArgMaxK': {
           0: reference_algebra.ClosedRecord({'arg': e, 'value': y}),
           1: 'Num',
           'logica_value': [e]
        },        
        'Range': {
           0: 'Num',
           'logica_value': ['Num']    
        },
        'Length': {
           0: 'Str',
           'logica_value': 'Num'
        },
        'Size': {
           0: ['Singular'],
           'logica_value': 'Num'
        },
        '-': {
           0: 'Num',
           'left': 'Num',
           'right': 'Num',
           'logica_value': 'Num'
        },
        'Min': {
           0: x,
           'logica_value': x
        },
        'Sum': {
           0: 'Num',
           'logica_value': 'Num'
        },
        'Avg': {
           0: 'Num',
           'logica_value': 'Num'
        },
        'Max': {
           0: x,
           'logica_value': x
        },
        'Array': {
           0: reference_algebra.ClosedRecord({'arg': x, 'value': e}),
           'logica_value': [e]
        },
        'ValueOfUnnested': {
           0: x,
           'logica_value': x
        },
        'RecordAsJson': {
           0: reference_algebra.OpenRecord({}),
           'logica_value': 'Str'
        },
        '>': {
           'left': x,
           'right': x,
           'logica_value': 'Bool'
        },
        'ArrayConcat': {
           0: [e],
           1: [e],
           'logica_value': [e]
        },
        'Substr': {
           0: 'Str',
           1: 'Num',
           2: 'Num',
           'logica_value': 'Str'
        },
        'Fingerprint': {
           0: 'Str',
           'logica_value': 'Num'
        },
        'Abs': {
           0: 'Num',
           'logica_value': 'Num'
        },
        '!': {
           0: 'Bool',
           'logica_value': 'Bool'
        },
        '||': {
           'left': 'Bool',
           'right': 'Bool',
           'logica_value': 'Bool'
        },
        'IsNull': {
           0: 'Any',
           'logica_value': 'Bool'
        },
        'ToString': {
           0: 'Any',
           'logica_value': 'Str'
        },
        'ToInt64': {
           0: 'Any',
           'logica_value': 'Num'
        },
        'ToFloat64': {
           0: 'Any',
           'logica_value': 'Num'
        },
        'AnyValue': {
           0: x,
           'logica_value': x
        },
        'Format': {
           0: 'Str',
           1: 'Any', 2: 'Any', 3: 'Any', 4: 'Any', 5: 'Any', 6: 'Any',
           'logica_value': 'Str'
        },
        'Split': {
           0: 'Str',
           1: 'Str',
           'logica_value': ['Str']
        },
        'Element': {
           0: list_of_e,
           1: 'Num',
           'logica_value': e
        },
        'MagicalEntangle': {
           0: x,
           1: 'Any',
           'logica_value': x
        },
        'Count': {
           0: 'Any',
           'logica_value': 'Num'
        },
        '1': {
           0: x,
           'logica_value': x
        },
        'Least': {
           0: x,
           1: x,
           'logica_value': x
        },
        'Greatest': {
           0: x,
           1: x,
           'logica_value': x
        },
        'CurrentTimestamp': {
           'logica_value': 'Time'
        },
        'Coalesce': {
           0: x,
           1: x,
           2: x,
           3: x,
           'logica_value': x
        }
    }
    types_of_predicate['<'] = types_of_predicate['<='] = types_of_predicate['>='] = types_of_predicate['>']
    types_of_predicate['Sin'] = types_of_predicate['Cos'] = types_of_predicate['Log'
      ] = types_of_predicate['Exp'] = types_of_predicate['Abs']
    types_of_predicate['%'] = types_of_predicate['/'] = types_of_predicate['*']
    types_of_predicate['&&'] = types_of_predicate['||']
    return {
        p: {k: reference_algebra.TypeReference(v)
            for k, v in types.items()}
        for p, types in types_of_predicate.items()
    }
