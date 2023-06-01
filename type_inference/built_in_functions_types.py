from collections import defaultdict

from type_inference.types.variable_types import ListType, NumberType, StringType

built_in = defaultdict(dict)
number_type = NumberType()
string_type = StringType()

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
