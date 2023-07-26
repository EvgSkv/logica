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

# These are auxiliary definitions for reasoning about types in Logica.

from common.platonic import *

# Value type:
LogicalType = PlatonicObject({})

LogicalField = PlatonicObject({
    'field_name': Str,
    'field_value': LogicalType
})

LogicalRecord = PlatonicObject({
    'field': [LogicalField],
    'is_open': Bool,
})

LogicalList = PlatonicObject({
    'element': LogicalType
})

LogicalType.fields = {
    'can_be_anything': Bool,
    'atomic_type_name': Str,
    'list': LogicalList,
    'record': LogicalRecord,
}

# Type graph:
LogicalTypingContext = PlatonicObject({
    'start_in_program': Int,
    'end_in_program': Int,
})

LogicalTypingLiteral = PlatonicObject({
    'the_literal': Str,
})

LogicalTypingPredicateField = PlatonicObject({
    'predicate_name': Str,
    'field_name': Str,
    'index': Int,
})

LogicalTypingPredicateCall = PlatonicObject({
    'predicate_call_id': Int,
    'predicate_name': Str,
    'subscript_field': Str,
    'is_output': Bool,
})

LogicalTypingPredicateFieldAddressing = PlatonicObject({
    'predicate_call_id': Int,
    'field_name': Str,
})

LogicalTypingExpression = PlatonicObject({
    'variable_name': Str,
    'literal': LogicalTypingLiteral,
    'predicate_field': LogicalTypingPredicateFieldAddressing,
})

LogicalTypingExpressionDefinition = PlatonicObject({
    'expression_id': Int,
    'expression': LogicalTypingExpression,
})

LogicalTypingEquality = PlatonicObject({
    'left_hand_side': Int,
    'right_hand_side': Int,
})

LogicalTypingEqualityOfField = PlatonicObject({
    'record_expression_id': Int,
    'field_name': Str,
    'value_expression_id': Int,
})

LogicalTypingEqualityOfElement = PlatonicObject({
    'list_expression_id': Int,
    'element_expression_id': Int,
})

LogicalTypingKnownType = PlatonicObject({
    'expression_id': Int,
    'type_definition': LogicalType,
})

LogicalTypingHyperedge = PlatonicObject({
    'equality': LogicalTypingEquality,
    'impossible_equality': LogicalTypingEquality,
    'equality_of_field': LogicalTypingEqualityOfField,
    'equality_of_element': LogicalTypingEqualityOfElement,
    'known_type': LogicalTypingKnownType,
    'context': LogicalTypingContext,
})

LogicalTypeHyperGraph = PlatonicObject({
    'expressions': [LogicalTypingExpressionDefinition],
    'predicate_call': [LogicalTypingPredicateCall],
    'hyperedges': [LogicalTypingHyperedge],
})
