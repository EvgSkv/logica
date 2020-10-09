#!/usr/bin/python
#
# Copyright 2020 Google LLC
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

"""Compiler of a Logica expression to SQL."""

import copy

import json

from common import color
from common.data import processed_functions

from compiler import dialects


class QL(object):
  """Class translating Logica expressions into SQL."""
  BUILT_IN_FUNCTIONS = {  # Please keep sorted alphabetically.
      # Casting.
      'ToFloat64': 'CAST(%s AS FLOAT64)',
      'ToInt64': 'CAST(%s AS INT64)',
      'ToUInt64': 'CAST(%s AS UINT64)',
      'ToString': 'CAST(%s AS STRING)',
      # Aggregation.
      'Aggregate': '%s',  # Placeholder to use formulas for aggregation.
      'Agg+': 'SUM(%s)',
      'Agg++': 'ARRAY_CONCAT_AGG(%s)',
      # ArgMax and ArgMin return arg which achieves the max/min value.
      'ArgMax': 'ARRAY_AGG({0}.arg order by {0}.value desc limit 1)[OFFSET(0)]',
      # ArgMaxK and ArgMinK return arg **and** value for K elements that achieve
      # Max/Min value. It's not ideal that ArgMax and ArgMaxK return different
      # types, but having values could be useful sometimes and so we'd have to
      # introduce SortedLimitedList, which would be hard to remember.
      'ArgMaxK':
          'ARRAY_AGG({0} order by {0}.value desc limit {1})',
      'ArgMin': 'ARRAY_AGG({0}.arg order by {0}.value limit 1)[OFFSET(0)]',
      'ArgMinK':
          'ARRAY_AGG({0} order by {0}.value limit {1})',
      'Array': 'ARRAY_AGG({0}.value order by {0}.arg)',
      'Container': '%s',
      'Count': 'APPROX_COUNT_DISTINCT(%s)',
      'ExactCount': 'COUNT(DISTINCT %s)',
      'List': 'ARRAY_AGG(%s)',
      'Median': 'APPROX_QUANTILES(%s, 2)[OFFSET(1)]',
      'SomeValue': 'ARRAY_AGG(%s IGNORE NULLS LIMIT 1)[OFFSET(0)]',
      # Other functions.
      '!': 'NOT %s',
      '-': '- %s',
      'Concat': 'ARRAY_CONCAT({0}, {1})',
      'Constraint': '%s',
      'DateAddDay': 'DATE_ADD({0}, INTERVAL {1} DAY)',
      'DateDiffDay': 'DATE_DIFF({0}, {1}, DAY)',
      'Element': '{0}[OFFSET({1})]',
      'Enumerate': ('ARRAY(SELECT STRUCT('
                    'ROW_NUMBER() OVER () AS n, x AS element) '
                    'FROM UNNEST(%s) as x)'),
      'IsNull': '(%s IS NULL)',
      'Join': 'ARRAY_TO_STRING(%s)',
      'Like': '({0} LIKE {1})',
      'Range': 'GENERATE_ARRAY(0, %s - 1)',
      'RangeOf': 'GENERATE_ARRAY(0, ARRAY_LENGTH(%s) - 1)',
      'Set': 'ARRAY_AGG(DISTINCT %s)',
      'Size': 'ARRAY_LENGTH(%s)',
      'Sort': 'ARRAY(SELECT x FROM UNNEST(%s) as x ORDER BY x)',
      'TimestampAddDays': 'TIMESTAMP_ADD({0}, INTERVAL {1} DAY)',
      'Unique': 'ARRAY(SELECT DISTINCT x FROM UNNEST(%s) as x ORDER BY x)',
      # These functions are treated specially.
      'FlagValue': 'UNUSED',
      'Cast': 'UNUSED',
      'SqlExpr': 'UNUSED'
  }
  BUILT_IN_INFIX_OPERATORS = {
      '==': '%s = %s',
      '<=': '%s <= %s',
      '<': '%s < %s',
      '>=': '%s >= %s',
      '>': '%s > %s',
      '->': 'STRUCT(%s AS arg, %s as value)',
      '/': '(%s) / (%s)',
      '+': '(%s) + (%s)',
      '-': '(%s) - (%s)',
      '*': '(%s) * (%s)',
      '^': 'POW(%s, %s)',
      '!=': '%s != %s',
      '++': 'CONCAT(%s, %s)',
      'In': '%s IN UNNEST(%s)',
      '||': '%s OR %s',
      '&&': '%s AND %s',
      '%': 'MOD(%s, %s)'
  }
  BULK_FUNCTIONS = {}
  BULK_FUNCTIONS_ARITY_RANGE = {}

  # When adding any analytic functions please check that ConvertAnalytic
  # function handles them correctly.
  ANALYTIC_FUNCTIONS = {
      'CumulativeSum':
          'SUM({0}) OVER (PARTITION BY {1} ORDER BY {2} '
          'ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)',
      'CumulativeMax':
          'MAX({0}) OVER (PARTITION BY {1} ORDER BY {2} '
          'ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)',
      'CumulativeMin':
          'MIN({0}) OVER (PARTITION BY {1} ORDER BY {2} '
          'ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)',
      'WindowSum':
          'SUM({0}) OVER (PARTITION BY {1} ORDER BY {2} '
          'ROWS BETWEEN {3} PRECEDING AND CURRENT ROW)',
      'WindowMax':
          'MAX({0}) OVER (PARTITION BY {1} ORDER BY {2} '
          'ROWS BETWEEN {3} PRECEDING AND CURRENT ROW)',
      'WindowMin':
          'MIN({0}) OVER (PARTITION BY {1} ORDER BY {2} '
          'ROWS BETWEEN {3} PRECEDING AND CURRENT ROW)',
  }

  def __init__(self, vars_vocabulary, subquery_translator, exception_maker,
               flag_values, custom_udfs=None, dialect=None):
    """Initializes the instance.

    Args:
      vars_vocabulary: Dictionary mapping Logica variable to an SQL expression.
      subquery_translator: SubqueryTranslator to translate 'combine'
        expressions.
      exception_maker: Exception to raise if expression comilation error occurs.
      flag_values: Values of program flags.
      custom_udfs: A map from udf name to udf application string template.
      dialect: SQL dialect object.
    """
    self.dialect = dialect or dialects.BigQueryDialect()
    self.vocabulary = vars_vocabulary
    self.subquery_translator = subquery_translator
    # Using instance variables for test purposes.
    self.InstallBulkFunctionsOfStandardSQL()
    self.bulk_functions = self.BULK_FUNCTIONS
    self.bulk_function_arity_range = self.BULK_FUNCTIONS_ARITY_RANGE
    self.built_in_functions = copy.deepcopy(self.bulk_functions)
    self.built_in_functions.update(self.BUILT_IN_FUNCTIONS)
    self.built_in_functions.update(self.dialect.BuiltInFunctions())
    self.built_in_infix_operators = copy.deepcopy(
        self.BUILT_IN_INFIX_OPERATORS)
    self.built_in_infix_operators.update(self.dialect.InfixOperators())
    self.exception_maker = exception_maker
    self.debug_undefined_variables = False
    # We set convert_to_json to convert arguments of annotations to Python
    # objects. This is hack-y. In the long run we plan to run them in
    # StandardSQL reference implementation and record the output.
    self.convert_to_json = False
    self.flag_values = flag_values
    self.custom_udfs = custom_udfs or {}

  @classmethod
  def BasisFunctions(cls):
    cls.InstallBulkFunctionsOfStandardSQL()
    return (
        set(cls.BUILT_IN_FUNCTIONS) |
        set(cls.BUILT_IN_INFIX_OPERATORS) |
        set(cls.BULK_FUNCTIONS) |
        set(cls.ANALYTIC_FUNCTIONS))

  @classmethod
  def InstallBulkFunctionsOfStandardSQL(cls):
    """Populates fields from processed_functions.csv."""
    if cls.BULK_FUNCTIONS:
      return
    def CamelCase(s):
      s = s.replace('.', '_')
      return ''.join(p[0].upper() + p[1:] for p in s.split('_'))
    reader = processed_functions.GetCsv()
    header = next(reader)

    for row in reader:
      row = dict(list(zip(header, row)))
      if row['function'][0] == '$':
        # TODO: Process operators.
        continue
      function_name = CamelCase(row['function'])
      cls.BULK_FUNCTIONS[function_name] = (
          '%s(%s)' % (row['sql_function'], '%s'))
      cls.BULK_FUNCTIONS_ARITY_RANGE[function_name] = (
          int(row['min_args']),
          float('inf')
          if row['has_repeated_args'] == '1' else int(row['max_args']))

  def BuiltInFunctionArityRange(self, f):
    """Returns arity of the built-in function."""
    assert f in self.built_in_functions
    if f in self.BUILT_IN_FUNCTIONS:
      if f == 'If':
        return (3, 3)
      arity_2_functions = ['RegexpExtract', 'Like',
                           'ParseTimestamp', 'FormatTimestamp',
                           'TimestampAddDays', 'Split', 'Element',
                           'Concat', 'DateAddDay', 'DateDiffDay',
                           'ArgMaxK', 'ArgMinK', 'Join']
      if f in arity_2_functions:
        return (2, 2)
      return (1, 1)
    else:
      assert f in self.bulk_functions
      return self.bulk_function_arity_range[f]

  def If(self, args):
    assert len(args) == 3
    return 'IF(%s, %s, %s)' % tuple(args)

  def Function(self, f, args):
    args_list = [None] * len(args)
    for k, v in args.items():
      args_list[k] = str(v)
    if '%s' in f:
      return f % ', '.join(args_list)
    else:
      return f.format(*args_list)

  def Infix(self, op, args):
    return op % (args['left'], args['right'])

  def Subscript(self, record, subscript):
    if isinstance(subscript, int):
      subscript = 'col%d' % subscript
    return '%s.%s' % (record, subscript)

  def IntLiteral(self, literal):
    return str(literal['number'])

  def StrLiteral(self, literal):
    if self.dialect.Name() == "PostgreSQL":
      # TODO: Do this safely.
      return '\'%s\'' % literal['the_string']
    return json.dumps(literal['the_string'], ensure_ascii=False)

  def ListLiteralInternals(self, literal):
    return ', '.join([self.ConvertToSql(e)
                      for e in literal['element']])

  def ListLiteral(self, literal):
    return 'ARRAY[%s]' % self.ListLiteralInternals(literal)

  def BoolLiteral(self, literal):
    return literal['the_bool']

  def NullLiteral(self, literal):
    return literal['the_null']

  # Might be used for automatic program analysis.
  def PredicateLiteral(self, literal):
    if self.convert_to_json:
      return '{"predicate_name": "%s"}' % (literal['predicate_name'])
    return 'STRUCT("%s" AS predicate_name)' % literal['predicate_name']

  def Variable(self, variable):
    if variable['var_name'] in self.vocabulary:
      return self.vocabulary[variable['var_name']]
    else:
      if self.debug_undefined_variables:
        return 'UNDEFINED_%s' % variable['var_name']
      assert False, 'Found no interpretation for %s in %s' % (
          variable['var_name'], self.vocabulary)

  def ConvertRecord(self, args):
    result = {}
    for f_v in args['field_value']:
      assert 'expression' in f_v['value'], (
          'Bad record: %s' % args)
      result[f_v['field']] = self.ConvertToSql(f_v['value']['expression'])
    return result

  def RecordAsJson(self, record):
    json_field_values = []
    for f_v in record['field_value']:
      json_field_values.append('"{field}": {value}'.format(
          field=f_v['field'],
          value=self.ConvertToSql(f_v['value']['expression'])))
    return '{%s}' % ', '.join(json_field_values)

  def Record(self, record):
    if self.convert_to_json:
      return self.RecordAsJson(record)
    arguments_str = ', '.join(
        '%s AS %s' % (self.ConvertToSql(f_v['value']['expression']),
                      f_v['field'])
        for f_v in record['field_value'])
    return 'STRUCT(%s)' % arguments_str

  def GenericSqlExpression(self, record):
    """Converting SqlExpr to SQL."""
    top_record = self.ConvertRecord(record)
    if set(top_record) != set([0, 1]):
      raise self.exception_maker(
          'SqlExpr must have 2 positional arguments, got: %s' % top_record)
    if ('literal' not in record['field_value'][0]
        ['value']['expression'] or
        'the_string' not in
        record['field_value'][0]['value']['expression']['literal']):
      raise self.exception_maker(
          'SqlExpr must have first argument be string, got: %s' %
          top_record[0])

    template = (
        record['field_value'][0]['value']['expression']['literal']
        ['the_string']['the_string'])
    if 'record' not in record['field_value'][1]['value']['expression']:
      raise self.exception_maker(
          'Sectond argument of SqlExpr must be record literal. Got: %s' %
          top_record[1])
    args = self.ConvertRecord(
        record['field_value'][1]['value']['expression']['record'])
    return template.format(**args)

  def Implication(self, implication):
    when_then_clauses = []
    for cond_cons in implication['if_then']:
      when_then_clauses.append(
          'WHEN {cond} THEN {cons}'.format(
              cond=self.ConvertToSql(cond_cons['condition']),
              cons=self.ConvertToSql(cond_cons['consequence'])))
    when_then_clauses_str = ' '.join(when_then_clauses)
    otherwise = self.ConvertToSql(implication['otherwise'])
    return 'CASE %s ELSE %s END' % (when_then_clauses_str, otherwise)

  def ConvertAnalyticListArgument(self, expression):
    if ('literal' not in expression or
        'the_list' not in expression['literal']):
      raise self.exception_maker(
          'Analytic list argument must resolve to list literal, got: %s' %
          self.ConvertToSql(expression))
    return self.ListLiteralInternals(expression['literal']['the_list'])

  def ConvertAnalytic(self, call):
    """Converting analytic function call to SQL."""
    is_window = call['predicate_name'].startswith('Window')
    if len(call['record']['field_value']) != 3 + is_window:
      raise self.exception_maker(
          'Function %s must have %d arguments.' % (call['predicate_name'],
                                                   3 + is_window))
    aggregant = self.ConvertToSql(
        call['record']['field_value'][0]['value']['expression'])
    group_by = self.ConvertAnalyticListArgument(
        call['record']['field_value'][1]['value']['expression'])
    order_by = self.ConvertAnalyticListArgument(
        call['record']['field_value'][2]['value']['expression'])

    if is_window:
      window_size = self.ConvertToSql(
          call['record']['field_value'][3]['value']['expression'])

    if not is_window:
      return self.ANALYTIC_FUNCTIONS[call['predicate_name']].format(
          aggregant, group_by, order_by)
    else:
      return self.ANALYTIC_FUNCTIONS[call['predicate_name']].format(
          aggregant, group_by, order_by, window_size)

  def ConvertToSql(self, expression):
    """Converting Logica expression into SQL."""
    # print('EXPR:', expression)
    # Variables.
    if 'variable' in expression:
      return self.Variable(expression['variable'])

    # Literals.
    if 'literal' in expression:
      literal = expression['literal']
      if 'the_number' in literal:
        return self.IntLiteral(literal['the_number'])
      if 'the_string' in literal:
        return self.StrLiteral(literal['the_string'])
      if 'the_list' in literal:
        return self.ListLiteral(literal['the_list'])
      if 'the_bool' in literal:
        return self.BoolLiteral(literal['the_bool'])
      if 'the_null' in literal:
        return self.NullLiteral(literal['the_null'])
      if 'the_predicate' in literal:
        return self.PredicateLiteral(literal['the_predicate'])
      assert False, 'Logica bug: unsupported literal parsed: %s' % literal

    if 'call' in expression:
      call = expression['call']
      arguments = self.ConvertRecord(call['record'])
      if call['predicate_name'] in self.ANALYTIC_FUNCTIONS:
        return self.ConvertAnalytic(call)
      if call['predicate_name'] == 'SqlExpr':
        return self.GenericSqlExpression(call['record'])
      if call['predicate_name'] == 'Cast':
        if (len(arguments) != 2 or
            'literal' not in
            call['record']['field_value'][1]['value']['expression'] or
            'the_string' not in
            call['record']['field_value'][1]['value']['expression']['literal']):
          raise self.exception_maker(
              'Cast must have 2 arguments and the second argument must be a '
              'string literal.')
        cast_to = (
            call['record']['field_value'][1]['value']['expression']['literal']
            ['the_string']['the_string'])
        return 'CAST(%s AS %s)' % (
            self.ConvertToSql(
                call['record']['field_value'][0]['value']['expression']),
            cast_to)

      if call['predicate_name'] == 'FlagValue':
        if (len(arguments) != 1 or
            'literal' not in
            call['record']['field_value'][0]['value']['expression'] or
            'the_string' not in
            call['record']['field_value'][0]['value']['expression']['literal']):
          raise self.exception_maker(
              'FlagValue argument must be a string literal.')
        flag = (
            call['record']['field_value'][0]['value']['expression']['literal']
            ['the_string']['the_string'])
        if flag not in self.flag_values:
          raise self.exception_maker(
              'Unspecified flag: %s' % flag)
        return self.StrLiteral(
            {'the_string': self.flag_values[flag]})
      for ydg_f, sql_f in self.built_in_functions.items():
        if call['predicate_name'] == ydg_f:
          if not sql_f:
            raise self.exception_maker(
                'Function %s is not supported by %s dialect.' % (
                    color.Warn(ydg_f), color.Warn(self.dialect.Name())))
          if len(arguments) == 2 and ydg_f == '-':
            continue  # '-' is the only operator with variable arity.
          arity_range = self.BuiltInFunctionArityRange(ydg_f)
          if not arity_range[0] <= len(arguments) <= arity_range[1]:
            raise self.exception_maker(
                color.Format(
                    'Built-in function {warning}{ydg_f}{end} takes {a} '
                    'arguments, but {b} arguments were given.',
                    dict(ydg_f=ydg_f, a=arity_range,
                         b=len(arguments))))
          return self.Function(sql_f, arguments)

      for udf, udf_sql in self.custom_udfs.items():
        if call['predicate_name'] == udf:
          # TODO: Treatment of positional arguments should be
          # simplified everywhere.
          arguments = dict(
              (k, v) if isinstance(k, str) else ('col%d' % k, v)
              for k, v in arguments.items())
          try:
            result = udf_sql.format(**arguments)
          except KeyError:
            raise self.exception_maker(
                'Function %s call is inconsistent with its signature %s.' %
                (color.Warn(udf), udf_sql))
          return result

      for ydg_op, sql_op in self.built_in_infix_operators.items():
        if call['predicate_name'] == ydg_op:
          result = self.Infix(sql_op, arguments)
          # TODO: Don't add parenthesis unless they are needed.
          if ydg_op not in ('++', '++?', 'In', '=='):
            result = '(' + result + ')'
          return result

    if 'subscript' in expression:
      sub = expression['subscript']
      subscript = sub['subscript']['literal']['the_symbol']['symbol']
      # TODO: Record literal and record of subscript should have
      # different keys.
      # Try to opimize and return the field from a record.
      if 'record' in sub['record']:
        for f_v in sub['record']['record']['field_value']:
          if f_v['field'] == subscript:
            # Optimizing and returning the field directly.
            return self.ConvertToSql(f_v['value']['expression'])
      # Couldn't optimize, just return the '.' expression.
      record = self.ConvertToSql(sub['record'])
      return self.Subscript(record, subscript)

    if 'record' in expression:
      record = expression['record']
      return self.Record(record)

    if 'combine' in expression:
      return '(%s)' % (
          self.subquery_translator.TranslateRule(expression['combine'],
                                                 self.vocabulary))

    if 'implication' in expression:
      implication = expression['implication']
      return self.Implication(implication)

    if 'call' in expression and 'predicate_name' in expression['call']:
      raise self.exception_maker(color.Format(
          'Unsupported supposedly built-in function: '
          '{warning}{predicate}{end}.', dict(
              predicate=expression['call']['predicate_name'])))
    assert False, (
        'Logica bug: expression %s failed to compile for unknown reason.' %
        str(expression))
