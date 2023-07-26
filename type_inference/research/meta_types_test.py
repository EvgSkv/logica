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

import unittest

from type_inference.research import meta_types

class MetaTypesTest(unittest.TestCase):
  def testLogicalType(self):
    r = (
        {'record': 
            {'field': 
            [{'field_name': 'a', 
                'field_value': {'can_be_anything': True}}]}})
    print('Logical type example:', meta_types.LogicalType(r))
    print('Adherence:', meta_types.LogicalType.AdheredBy(r) )

  def testHyperaphType1(self):
    type_hypergraph_example = {
        'expressions': [
            {'expression_id': 1, 'expression': {'variable_name': 'x'}},
            {'expression_id': 2, 'expression': {'variable_name': 'y'}},
            {'expression_id': 3, 'expression': {'predicate_field': {'predicate_call_id': 1, 'field_name': 'left'}}},
            {'expression_id': 4, 'expression': {'predicate_field': {'predicate_call_id': 1, 'field_name': 'right'}}},
            {'expression_id': 5, 'expression': {'predicate_field': {'predicate_call_id': 2, 'field_name': 'col0'}}},
            {'expression_id': 6, 'expression': {'predicate_field': {'predicate_call_id': 3, 'field_name': 'col0'}}},
        ],
        'predicate_call': [
            {'predicate_call_id': 1, 'predicate_name': '+'},
            {'predicate_call_id': 2, 'predicate_name': 'T'},
            {'predicate_call_id': 3, 'predicate_name': 'T'},
        ],
        'hyperedges': [
            {'equality': {'left_hand_side': 1, 'right_hand_side': 3}},
            {'equality': {'left_hand_side': 2, 'right_hand_side': 4}},
            {'equality': {'left_hand_side': 1, 'right_hand_side': 5}},
            {'equality': {'left_hand_side': 2, 'right_hand_side': 6}},
        ],
    }
    print('Hypergraph example 1:', 
          meta_types.LogicalTypeHyperGraph(type_hypergraph_example))

  def testHypergraphType2(self):
    type_hypergraph_example = {
        'expressions': [
            {'expression_id': 1, 'expression': {'variable_name': 'x'}},
            {'expression_id': 2, 'expression': {'variable_name': 'y'}},
            {'expression_id': 3, 'expression': {'predicate_field': {'predicate_call_id': 1, 'field_name': 'col0'}}},
            {'expression_id': 4, 'expression': {'predicate_field': {'predicate_call_id': 2, 'field_name': 'col0'}}},
            {'expression_id': 5, 'expression': {'predicate_field': {'predicate_call_id': 2, 'field_name': 'logica_value'}}},
            {'expression_id': 6, 'expression': {'predicate_field': {'predicate_call_id': 3, 'field_name': 'col0'}}},
            {'expression_id': 7, 'expression': {'predicate_field': {'predicate_call_id': 3, 'field_name': 'logica_value'}}},
            {'expression_id': 8, 'expression': {'predicate_field': {'predicate_call_id': 4, 'field_name': 'left'}}},
            {'expression_id': 9, 'expression': {'predicate_field': {'predicate_call_id': 4, 'field_name': 'right'}}},
            {'expression_id': 10, 'expression': {'predicate_field': {'predicate_call_id': 4, 'field_name': 'logica_value'}}},
            {'expression_id': 11, 'expression': {'literal': {'the_literal': '1'}}},  # TODO: Represent literals better.
        ],
        'predicate_call': [
            {'predicate_call_id': 1, 'predicate_name': 'T', 'is_output': False},
            {'predicate_call_id': 2, 'predicate_name': 'Subscript', 'subscript_field': 'a', 'is_output': False},
            {'predicate_call_id': 3, 'predicate_name': 'Q', 'is_output': True},
            {'predicate_call_id': 4, 'predicate_name': '+', 'is_output': False},
        ],
        'hyperedges': [
            {'equality': {'left_hand_side': 1, 'right_hand_side': 3}},
            {'equality': {'left_hand_side': 1, 'right_hand_side': 4}},
            {'equality': {'left_hand_side': 5, 'right_hand_side': 7}},
            {'equality': {'left_hand_side': 2, 'right_hand_side': 6}},
            {'equality': {'left_hand_side': 5, 'right_hand_side': 8}},
            {'equality': {'left_hand_side': 11, 'right_hand_side': 9}},
            {'equality': {'left_hand_side': 2, 'right_hand_side': 10}},
        ],
    }
    print('Hypergraph example 2:', 
      meta_types.LogicalTypeHyperGraph(type_hypergraph_example))
