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

"""Parser of Logica."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import copy
import os
import re
import string
import sys
from typing import Dict, Iterator, List, Optional, Tuple

if '.' not in __package__:
  from common import color
else:
  from ..common import color

CLOSE_TO_OPEN = {
    ')': '(',
    '}': '{',
    ']': '['
}
CLOSING_PARENTHESIS = list(CLOSE_TO_OPEN.keys())
OPENING_PARENTHESIS = list(CLOSE_TO_OPEN.values())

VARIABLE_CHARS_SET = set(string.ascii_lowercase) | set('_') | set(string.digits)


class HeritageAwareString(str):
  """A string that remembers who's substring it is."""

  def __new__(cls, content) -> 'HeritageAwareString':
    if isinstance(content, str):
      return str.__new__(cls, content)
    assert isinstance(content, bytes), 'Unexpected content: %s' % repr(content)
    return str.__new__(cls, content.decode('utf-8'))

  def __init__(self, unused_content):
    self.start = 0
    self.stop = len(self)
    self.heritage = str(self)

  def __getitem__(self, slice_or_index) -> 'HeritageAwareString':
    if isinstance(slice_or_index, int):
      return HeritageAwareString(str.__getitem__(self, slice_or_index))
    else:
      assert isinstance(slice_or_index, slice)
      start = slice_or_index.start or 0
      stop = (
          slice_or_index.stop if slice_or_index.stop is not None else len(self))
    return self.GetSlice(start, stop)

  def GetSlice(self, start, stop) -> 'HeritageAwareString':
    substring = HeritageAwareString(str(self)[start:stop])
    if stop > len(self):
      stop = len(self)
    if stop < 0:
      stop = len(self) + stop
    substring.start = self.start + start
    substring.stop = self.start + stop
    substring.heritage = self.heritage
    return substring

  def Pieces(self):
    return (self.heritage[:self.start],
            self.heritage[self.start:self.stop],
            self.heritage[self.stop:])


class ParsingException(Exception):
  """Exception thrown by parsing."""

  def __init__(self, message, location):
    # TODO: Unify coloring approach between parsing and compiling.
    message = message.replace(
        '>>', color.Color('warning')).replace('<<', color.Color('end'))
    super(ParsingException, self).__init__(message)
    self.location = location

  def ShowMessage(self, stream=sys.stderr):
    """Printing error message."""
    print(color.Format('{underline}Parsing{end}:'), file=stream)
    before, error, after = self.location.Pieces()
    if len(before) > 300:
      before = before[-300:]
    if len(after) > 300:
      after = after[:300]
    if not error:
      error = '<EMPTY>'

    print(color.Format('{before}{warning}{error_text}{end}{after}',
                       dict(before=before,
                            error_text=error,
                            after=after)), file=stream)
    print(
        color.Format('\n[ {error}Error{end} ] ') + str(self), file=stream)


def FunctorSyntaxErrorMessage():
  return (
      'Incorrect syntax for functor call. '
      'Functor call to be made as\n'
      '  R := F(A: V, ...)\n'
      'or\n'
      '  @Make(R, F, {A: V, ...})\n'
      'Where R, F, A\'s and V\'s are all '
      'predicate names.')


def Traverse(s):
  """Traversing the string, yielding indices with the state of parentheses.

  Args:
    s: Logica.

  Yields:
    (index in the string,
     state of how many parenthesis do we have open,
     status 'OK' or 'Unmatched <something>')
    If 'Unmatched' status is yielded the program has a syntax error and compiler
    should inform the user. Yielding 'Unmatched' terminates the iterator.
  """
  state = ''
  def State():
    if not state:
      return ''
    return state[-1]

  idx = -1
  while idx + 1 < len(s):
    idx += 1
    c = s[idx]
    c2 = s[idx:(idx + 2)]  # For /*, */.
    c3 = s[idx:(idx + 3)]  # For """.

    # Deal with strings (without escape).
    # TODO: Deal with string escaping.
    track_parenthesis = True

    # First see if we are in a comment or a string.
    if State() == '#':
      track_parenthesis = False
      if c == '\n':
        state = state[:-1]
      else:
        # Comments are invisible to compiler.
        continue
    elif State() == '"':
      track_parenthesis = False
      if c == '\n':
        yield (idx, None, 'EOL in string')
      if c == '"':
        state = state[:-1]
    elif State() == '`':
      track_parenthesis = False
      if c == '`':
        state = state[:-1]
    elif State() == '3':
      track_parenthesis = False
      if c3 == '"""':
        state = state[:-1]
        yield (idx, state, 'OK')
        idx += 1
        yield (idx, state, 'OK')
        idx += 1
    elif State() == '/':
      track_parenthesis = False
      if c2 == '*/':
        state = state[:-1]
        idx += 1
      # Comments are invisible to compiler.
      continue
    else:
      # We are neither in comment nor in string.
      if c == '#':
        state += '#'
        # Comments are invisible to compiler.
        continue
      elif c3 == '"""':
        state += '3'
        yield (idx, state, 'OK')
        idx += 1
        yield (idx, state, 'OK')
        idx += 1
      elif c == '"':
        state += '"'
      elif c == '`':
        state += '`'
      elif c2 == '/*':
        state += '/'
        idx += 1
        # Comments are invisible to compiler.
        continue

    if track_parenthesis:
      if c in OPENING_PARENTHESIS:
        state += c
      elif c in CLOSING_PARENTHESIS:
        if state and state[-1] == CLOSE_TO_OPEN[c]:
          state = state[:-1]
        else:
          yield (idx, None, 'Unmatched')
          break
    yield (idx, state, 'OK')


def RemoveComments(s):
  chars = []
  for idx, unused_state, status in Traverse(s):
    if status == 'Unmatched':
      raise ParsingException('Parenthesis matches nothing.', s[idx:idx+1])
    elif status == 'EOL in string':
      raise ParsingException('End of line in string.', s[idx:idx])
    assert status == 'OK'
    chars.append(s[idx])
  return ''.join(chars)


def IsWhole(s):
  """String is 'whole' if all parenthesis match."""
  status = 'OK'
  for (_, _, status) in Traverse(s):
    pass
  return status == 'OK'


def ShowTraverse(s):
  """Showing states of traverse.

  A debugging tool.
  Args:
    s: string with Logica.
  """
  for idx, state, status in Traverse(s):
    print('-----')
    print(s)
    print(' ' * idx + '^ ~%s~/%s' % (state, status))


def Strip(s):
  """Removing outer parenthesis and spaces."""
  while True:
    s = StripSpaces(s)
    if (len(s) >= 2 and s[0] == '(' and s[-1] == ')' and
        IsWhole(s[1:-1])):
      s = s[1:-1]
    else:
      return s


def StripSpaces(s):
  left_idx = 0
  right_idx = len(s) - 1
  while left_idx < len(s) and s[left_idx].isspace():
    left_idx += 1
  while right_idx > left_idx and s[right_idx].isspace():
    right_idx -= 1
  return s[left_idx:right_idx + 1]


def SplitRaw(s, separator):
  """Splits the string on separator, respecting parenthesis.

  This is cornerstone of parsing.
  Example: Split("[a,b],[c,d]", ",") == ["[a,b]", "[c,d]"].

  Args:
    s: String with Logica.
    separator: Separator to split on.
  Returns:
    A list of parts of the string.
  Raises:
    ParsingException: When parenthesis don't match.
  """
  parts = []
  l = len(separator)
  traverse = Traverse(s)
  part_start = 0
  for idx, state, status in traverse:
    # TODO: This should be thrown by Traverse.
    if status != 'OK':
      raise ParsingException('Parenthesis matches nothing.', s[idx:idx+1])
    # TODO: This a terrible hack to avoid parsing || as two |. Maybe
    # we should tokenize at some point.
    if not state and s[idx:(idx + l)] == separator and (
        len(s) == idx + l or s[idx + l] != '|') and (
            idx == 0 or s[idx - 1] != '|'):
      # TODO: Treat tuples properly.
      parts.append(s[part_start:idx])
      for _ in range(l - 1):
        idx, state, status = next(traverse)
      part_start = idx + 1
  parts.append(s[part_start:])
  return parts


def Split(s, separator):
  parts = SplitRaw(s, separator)
  return [Strip(p) for p in parts]


def SplitInTwo(s, separator):
  """Splits the string in two or dies. Makes python typing happy."""
  parts = Split(s, separator)
  if len(parts) != 2:
    raise ParsingException(
        'I expected string to be split by >>%s<< in two.' % separator, s)

  return (parts[0], parts[1])


def SplitInOneOrTwo(s, separator):
  """Splits the string in one or two. Makes python typing happy."""
  parts = Split(s, separator)
  if len(parts) == 1:
    return ((parts[0],), None)
  elif len(parts) == 2:
    return (None, (parts[0], parts[1]))
  else:
    raise ParsingException(
        'String should have been split by >>%s<< in 1 or 2 pieces.' % (
            separator), s)


def SplitMany(ss: List[HeritageAwareString],
              separator: str) -> List[HeritageAwareString]:
  """Splits the list of strings by the separator, flattening the result."""
  result = []
  for s in ss:
    result.extend(Split(s, separator))
  return result


def SplitOnWhitespace(s: HeritageAwareString) -> List[HeritageAwareString]:
  """Split the string by whitespace.

  Like Split, does not split inside quoted strings and parentheses.  Only return
  non-empty parts.
  """
  ss = [s]
  for separator in ' \n\t':
    ss = SplitMany(ss, separator)
  return [chunk for chunk in ss if chunk]

############################################
#
#           Parsing functions.
#

def ParseRecord(s):
  s = Strip(s)
  if (len(s) >= 2 and
      s[0] == '{' and
      s[-1] == '}' and
      IsWhole(s[1:-1])):
    return ParseRecordInternals(s[1:-1], is_record_literal=True)


def ParseRecordInternals(s,
                         is_record_literal = False):
  """Parsing internals of a record."""
  s = Strip(s)
  if len(Split(s, ':-')) > 1:
    raise ParsingException(
        'Unexpected >>:-<< in record internals. '
        'If you apply a function to a >>combine<< statement, place it in '
        'auxiliary variable first.', location=s)
  if not s:
    return {'field_value': []}
  result = []
  if IsWhole(s):
    field_values = Split(s, ',')
    had_restof = False
    positional_ok = True
    observed_fields = []
    for idx, field_value in enumerate(field_values):
      if had_restof:
        raise ParsingException('Field >>..<rest_of><< must go last.',
                               field_value)
      if field_value.startswith('..'):
        if is_record_literal:
          raise ParsingException('Field >>..<rest_of> in record literals<< '
                                 'is not currently suppported .', field_value)
        item = {
            'field': '*',
            'value': {'expression': ParseExpression(field_value[2:])}
        }
        if observed_fields:
          item['except'] = observed_fields
        result.append(item)
        had_restof = True
        positional_ok = False
        continue
      (_, colon_split) = SplitInOneOrTwo(field_value, ':')
      if colon_split:
        positional_ok = False
        field, value = colon_split

        observed_field = field
        if not value:
          value = field
          if field and field[0] in string.ascii_uppercase:
            raise ParsingException('Record fields may not start with capital '
                                   'letter, as it is reserved for predicate '
                                   'literals.\nBacktick the field name if '
                                   'you need it capitalized. '
                                   'E.g. "Q(`A`: 1)".',
                                   field)

          if field and field[0] == '`':
            raise ParsingException('Backticks in variable names are '
                                   'disallowed. Please give an explicit '
                                   'variable for the value of the column.',
                                   field)

        result.append({
            'field': field,
            'value': {
                'expression': ParseExpression(value)
            }
        })
      else:
        (_, question_split) = SplitInOneOrTwo(field_value, '?')
        if question_split:
          positional_ok = False
          field, value = question_split
          observed_field = field
          if not field:
            raise ParsingException('Aggregated fields have to be named.',
                                   field_value)
          operator, expression = SplitInTwo(value, '=')
          operator = Strip(operator)
          result.append(
              {
                  'field': field,
                  'value': {
                      'aggregation': {
                          'operator': operator,
                          'argument': ParseExpression(expression)
                      }
                  }
              })
        else:
          if positional_ok:
            result.append(
                {
                    'field': idx,
                    'value': {
                        'expression': ParseExpression(field_value)
                    }
                })
            # It's not ideal that we hardcode 'col%d' logic here.
            observed_field = 'col%d' % idx
          else:
            raise ParsingException(
                'Positional argument can not go after non-positional '
                'arguments.', field_value)
      observed_fields.append(observed_field)

  return {'field_value': result}


def ParseVariable(s: HeritageAwareString):
  if (s and s[0] in set(string.ascii_lowercase) | set('_') and
      set(s) <= VARIABLE_CHARS_SET):
    return {'var_name': s}


def ParseNumber(s: HeritageAwareString):
  if s[-1:] == 'u':
    s = s[:-1]
  try:
    float(s)
  except ValueError:
    return None
  return {'number': s}


# TODO: Do this right, i.e. account for escaping and quotes in between.
def ParseString(s):
  if (len(s) >= 2 and
      s[0] == '"' and
      s[-1] == '"' and
      '"' not in s[1:-1]):
    return {'the_string': s[1:-1]}
  if (len(s) >= 6 and
      s[:3] == '"""' and
      s[-3:] == '"""' and
      '"""' not in s[3:-3]):
    return {'the_string': s[3:-3]}


def ParseBoolean(s):
  if s in ['true', 'false']:
    return {'the_bool': s}


def ParseNull(s):
  if s == 'null':
    return {'the_null': s}


def ParseList(s):
  """Parsing List literal."""
  if len(s) >= 2 and s[0] == '[' and s[-1] == ']' and IsWhole(s[1:-1]):
    inside = Strip(s[1:-1])
    if not inside:
      elements = []
    else:
      elements_str = Split(inside, ',')
      elements = [ParseExpression(e) for e in elements_str]
    return {'element': elements}
  else:
    return None


def ParsePredicateLiteral(s):
  if (s == '++?' or
      s == 'nil' or
      s and
      set(s) <=
      set(string.ascii_letters) | set(string.digits) | set(['_']) and
      s[0] in string.ascii_uppercase):
    return {'predicate_name': s}


def ParseLiteral(s):
  """Parses a literal."""
  v = ParseNumber(s)
  if v:
    return {'the_number': v}
  v = ParseString(s)
  if v:
    return {'the_string': v}
  v = ParseList(s)
  if v:
    return {'the_list': v}
  v = ParseBoolean(s)
  if v:
    return {'the_bool': v}
  v = ParseNull(s)
  if v:
    return {'the_null': v}
  v = ParsePredicateLiteral(s)
  if v:
    return {'the_predicate': v}


def ParseInfix(s, operators=None):
  """Parses an infix operator expression."""
  operators = operators or [
      '||', '&&', '->', '==', '<=', '>=', '<', '>', '!=',
      '++?', '++', '+', '-', '*', '/', '%', '^', ' in ', '!']
  unary_operators = ['-', '!']
  for op in operators:
    parts = SplitRaw(s, op)
    if len(parts) > 1:
      # Right is the rightmost operand and left are all the other operands.
      # This way we parse as follows:
      # a / b / c -> (a / b) / c
      left, right = (
          s[:parts[-2].stop - s.start], s[parts[-1].start - s.start:])
      left = Strip(left)
      right = Strip(right)
      if op in unary_operators and not left:
        return {
            'predicate_name': op,
            'record': ParseRecordInternals(right)
        }

      left_expr = ParseExpression(left)
      right_expr = ParseExpression(right)
      return {
          'predicate_name': op.strip(),
          'record': {
              'field_value': [
                  {
                      'field': 'left',
                      'value': {'expression': left_expr}
                  },
                  {
                      'field': 'right',
                      'value': {'expression': right_expr}
                  }
              ]
          }
      }


def BuildTreeForCombine(parsed_expression, operator, parsed_body, full_text):
  """Construct a tree for a combine expression from the parsed components."""
  aggregated_field_value = {
      'field': 'logica_value',
      'value': {
          'aggregation': {
              'operator': operator,
              'argument': parsed_expression
          }
      }
  }
  result = {
      'head': {
          'predicate_name': 'Combine',
          'record': {
              'field_value': [aggregated_field_value]
          }
      },
      'distinct_denoted': True,
      'full_text': full_text
  }
  if parsed_body:
    result['body'] = {'conjunction': parsed_body}
  return result


def ParseCombine(s: HeritageAwareString):
  """Parsing 'combine' expression."""
  if s.startswith('combine '):
    s = s[len('combine '):]
    _, value_body = SplitInOneOrTwo(s, ':-')
    if value_body:
      value, body = value_body
    else:
      value = s
      body = None
    operator, expression = SplitInTwo(value, '=')
    operator = Strip(operator)
    parsed_expression = ParseExpression(expression)
    parsed_body = ParseConjunction(body, allow_singleton=True) if body else None
    return BuildTreeForCombine(parsed_expression, operator, parsed_body, s)


def ParseConciseCombine(s: HeritageAwareString):
  """Parses a concise 'combine' expression.

  A concise combine expression consists is of the form 'x Op= expr' or  'x Op=
  expr :- body', where x must be a variable.  It is equivalent to 'x == (combine
  Op= expr)' or 'x == (combine Op= expr :- body)' respectively.
  """
  parts = Split(s, '=')
  if len(parts) == 2:
    lhs_and_op, combine = parts
    left_parts = SplitOnWhitespace(lhs_and_op)
    if len(left_parts) > 1:
      lhs = s[:left_parts[-2].stop - s.start]
      operator = left_parts[-1]
      # These operators actually arise from comparison expressions; if we get
      # them here, we should bail out.
      prohibited_operators = ['!', '<', '>']
      if operator in prohibited_operators:
        return None
      left_expr = ParseExpression(lhs)
      _, expression_body = SplitInOneOrTwo(combine, ':-')
      if expression_body:
        expression, body = expression_body
      else:
        expression = combine
        body = None
      parsed_expression = ParseExpression(expression)
      parsed_body = ParseConjunction(
          body, allow_singleton=True) if body else None
      right_expr = BuildTreeForCombine(parsed_expression, operator, parsed_body,
                                       s)
      return {
          'left_hand_side': left_expr,
          'right_hand_side': {
              'combine': right_expr
          }
      }



def ParseImplication(s):
  """Parses implication expression."""
  if s.startswith('if ') or s.startswith('if\n'):
    inner = s[3:]
    if_thens = Split(inner, 'else if')
    (last_if_then, last_else) = SplitInTwo(if_thens[-1], 'else')
    if_thens[-1] = last_if_then
    result_if_thens = []
    for condition_concequence in if_thens:
      condition, consequence = SplitInTwo(condition_concequence, 'then')
      result_if_thens.append({
          'condition': ParseExpression(condition),
          'consequence': ParseExpression(consequence)
      })
    last_else_parsed = ParseExpression(last_else)
    return {'if_then': result_if_thens, 'otherwise': last_else_parsed}


def ParseExpression(s):
  """Parsing logica.Expression."""
  v = ParseCombine(s)
  if v:
    return {'combine': v}
  v = ParseImplication(s)
  if v:
    return {'implication': v}
  v = ParseLiteral(s)
  if v:
    return {'literal': v}
  v = ParseVariable(s)
  if v:
    return {'variable': v}
  v = ParseRecord(s)
  if v:
    return {'record': v}
  v = ParseCall(s)
  if v:
    return {'call': v}
  v = ParseInfix(s)
  if v:
    return {'call': v}
  v = ParseSubscript(s)
  if v:
    return {'subscript': v}
  v = ParseNegationExpression(s)
  if v:
    return v  # ParseNegationExpression returns an expression.

  raise ParsingException('Could not parse expression of a value.', s)


def ParseInclusion(s):
  element_list_str = Split(s, ' in ')
  if len(element_list_str) == 2:
    return {'list': ParseExpression(element_list_str[1]),
            'element': ParseExpression(element_list_str[0])}


def ParseCall(s):
  """Parsing logica.PredicateCall."""
  s = Strip(s)
  predicate = ''
  idx = 0
  if not s:
    return None
  # Specialcasing -> operator for definition.
  if s.startswith('->'):
    idx = 2
    predicate = '->'
  else:
    for (idx, state, status) in Traverse(s):
      assert status == 'OK'
      if state == '(':
        good_chars = (
            set(string.ascii_letters) |
            set(['@', '_', '.', '$', '{', '}', '+', '-', '`']) |
            set(string.digits))
        if ((idx > 0 and set(s[:idx]) <= good_chars) or
            s[:idx] == '!' or
            s[:idx] == '++?' or
            idx >= 2 and s[0] == '`' and s[idx - 1] == '`'):
          predicate = s[:idx]
          break
        else:
          return None
      if state and state != '{' and state[0] != '`':
        return None
    else:
      return None
  if (s[idx] == '(' and
      s[-1] == ')' and
      IsWhole(s[idx + 1:-1])):
    return {'predicate_name': predicate,
            'record': ParseRecordInternals(s[idx + 1: -1])}


def ParseUnification(s):
  parts = Split(s, '==')
  if len(parts) == 2:
    left, right = (parts[0], parts[1])
    left_expr = ParseExpression(left)
    right_expr = ParseExpression(right)
    return {'left_hand_side': left_expr,
            'right_hand_side': right_expr}


def ParseProposition(s):
  """Parsing logica.ExistentialFormula."""
  c = ParseDisjunction(s)
  if c:
    return {'disjunction': c}
  str_conjuncts = Split(s, ',')
  c = ParseConjunction(s, allow_singleton=False)
  if len(str_conjuncts) > 1:
    return {'conjunction': c}

  c = ParseImplication(s)
  if c:
    raise ParsingException('If-then-else clause is only supported as an '
                           'expression, not as a proposition.', s)
  c = ParseCall(s)
  if c:
    return {'predicate': c}
  c = ParseInfix(s, operators=['&&', '||'])
  if c:
    return {'predicate': c}
  c = ParseUnification(s)
  if c:
    return {'unification': c}
  c = ParseInclusion(s)
  if c:
    return {'inclusion': c}
  c = ParseConciseCombine(s)
  if c:
    return {'unification': c}  # x f= (...) parses to x == (combine f= ...)
  c = ParseInfix(s)
  if c:
    return {'predicate': c}
  c = ParseNegation(s)
  if c:
    return c  # ParseNegation returns a proposition.
  raise ParsingException('Could not parse proposition.', s)


def ParseConjunction(s, allow_singleton=False):
  str_conjuncts = Split(s, ',')
  if len(str_conjuncts) == 1 and not allow_singleton:
    return None
  conjuncts = []
  for c in str_conjuncts:
    c = ParseProposition(c)
    conjuncts.append(c)
  return {'conjunct': conjuncts}


def ParseDisjunction(s):
  str_disjuncts = Split(s, '|')
  if len(str_disjuncts) == 1:
    return None
  disjuncts = []
  for d in str_disjuncts:
    d = ParseProposition(d)
    disjuncts.append(d)
  return {'disjunct': disjuncts}


def ParseNegationExpression(s: HeritageAwareString):
  proposition = ParseNegation(s)
  if not proposition:
    return None
  expression = {'call': proposition['predicate']}
  return expression


def ParseNegation(s: HeritageAwareString):
  """Parsing negation as IsNull(combine...) expression."""
  space_and_negated = Split(s, '~')
  if len(space_and_negated) == 1:
    return None
  if len(space_and_negated) != 2 or space_and_negated[0]:
    raise ParsingException('Negation "~" is a unary operator.', s)
  _, negated = space_and_negated
  negated = Strip(negated)
  # TODO: It so happened that body of the predicate has to be a
  # conjunction. This should probably be simplified, any proposition
  # should be allowed to be a body.
  negated_proposition = {
      'conjunction': ParseConjunction(negated, allow_singleton=True)
  }

  number_one = {
      'literal': {
          'the_number': {
              'number': '1'
          }
      }
  }
  # Returning syntax tree of IsNull(combine Min= 1 :- <negated proposition>)
  return  {
      'predicate': {
          'predicate_name': 'IsNull',
          'record': {
              'field_value': [{
                  'field': 0,
                  'value': {
                      'expression': {
                          'combine': {
                              'body': negated_proposition,
                              'distinct_denoted': True,
                              'full_text': s,
                              'head': {
                                  'predicate_name': 'Combine',
                                  'record': {
                                      'field_value': [{
                                          'field': 'logica_value',
                                          'value': {
                                              'aggregation': {
                                                  'operator': 'Min',
                                                  'argument': number_one
                                              }
                                          }
                                      }]
                                  }
                              }
                          }
                      }
                  }
              }]
          }
      }
  }


def ParseSubscript(s: HeritageAwareString):
  """Parsing subscript expression."""
  str_path = SplitRaw(s, '.')
  if len(str_path) >= 2:
    record_str = s[:(str_path[-2].stop - s.start)]
    record_str_doublecheck = '.'.join(str_path[:-1])
    assert record_str == record_str_doublecheck, 'This should not happen.'
    record = ParseExpression(Strip(record_str))
    if not set(str_path[-1]) <= (set(string.ascii_lowercase) | set('_')
                                 | set(string.digits)):
      raise ParsingException('Subscript must be lowercase.', s)
    subscript = {'literal': {'the_symbol': {'symbol': str_path[-1]}}}
    return {'record': record, 'subscript': subscript}


def ParseHeadCall(s):
  """Parsing rule head, excluding 'distinct'."""
  saw_open = False
  idx = -1
  for idx, state, status in Traverse(s):
    if status != 'OK':
      raise ParsingException('Parenthesis matches nothing.', s[idx:idx+1])
    if state == '(':
      saw_open = True
    if saw_open and not state:
      break
  else:
    raise ParsingException('Found no call in rule head.', s)
  assert idx > 0
  call_str = s[:(idx + 1)]
  post_call_str = s[idx + 1:]
  call = ParseCall(call_str)
  if not call:
    raise ParsingException('Could not parse predicate call.', call_str)
  operator_expression = Split(post_call_str, '=')
  if len(operator_expression) == 1:
    if operator_expression[0]:
      raise ParsingException('Unexpected text in the head of a rule.',
                             operator_expression[0])
    return (call, False)
  # We have a value!
  if len(operator_expression) > 2:
    raise ParsingException('Too many \'=\' in predicate value.', post_call_str)

  assert len(operator_expression) == 2
  operator_str, expression_str = (operator_expression[0],
                                  operator_expression[1])

  if not operator_str:
    call['record']['field_value'].append({
        'field': 'logica_value',
        'value': {'expression': ParseExpression(expression_str)}
    })
    return (call, False)

  aggregated_field_value = {
      'field': 'logica_value',
      'value': {
          'aggregation': {
              'operator': operator_str,
              'argument': ParseExpression(expression_str)
          }
      }
  }
  call['record']['field_value'].append(aggregated_field_value)

  return (call, True)


def ParseFunctorRule(s):
  """Parsing functor rule, converting to '@Make' form."""
  parts = Split(s, ':=')
  if len(parts) != 2:
    return None
  new_predicate = ParseExpression(parts[0])
  definition_expr = ParseExpression(parts[1])
  if 'call' not in definition_expr:
    raise ParsingException(FunctorSyntaxErrorMessage(), parts[1])
  definition = definition_expr['call']
  if ('literal' not in new_predicate or
      'the_predicate' not in new_predicate['literal']):
    raise ParsingException(FunctorSyntaxErrorMessage(), parts[0])

  applicant = {
      'expression': {
          'literal': {
              'the_predicate': {
                  'predicate_name': definition['predicate_name']
              }
          }
      }
  }
  arguments = {'expression': {'record': definition['record']}}
  rule = {
      'full_text': s,
      'head': {
          'predicate_name': '@Make',
          'record': {
              'field_value': [
                  {'field': 0, 'value': {'expression': new_predicate}},
                  {'field': 1, 'value': applicant},
                  {'field': 2, 'value': arguments}
              ]
          }
      }
  }
  return rule


def ParseFunctionRule(s: HeritageAwareString) -> Optional[List[Dict]]:
  """Parsing functor rule, converting to '@Make' form."""
  parts = SplitRaw(s, '-->')
  if len(parts) != 2:
    return None
  this_predicate_call = ParseCall(parts[0])
  if not this_predicate_call:
    raise ParsingException('Left hand side of function definition must be '
                           'a predicate call.', parts[0])
  annotation = (
      ParseRule(HeritageAwareString(
          '@CompileAsUdf(%s)' % this_predicate_call['predicate_name'])))
  rule = ParseRule(HeritageAwareString(parts[0] + ' = ' + parts[1]))
  return [annotation, rule]


def ParseRule(s: HeritageAwareString) -> Dict:
  """Parsing logica.Logica."""
  parts = Split(s, ':-')
  if len(parts) > 2:
    raise ParsingException('Too many :- in a rule. '
                           'Did you forget >>semicolon<<?', s)
  head = parts[0]
  head_distinct = Split(head, 'distinct')
  if len(head_distinct) == 1:
    parsed_head_call, is_distinct = ParseHeadCall(head)
    if not parsed_head_call:
      raise ParsingException(
          'Could not parse head of a rule.', head)
    result = {'head': parsed_head_call}
    if is_distinct:
      result['distinct_denoted'] = True
  else:
    if not (len(head_distinct) == 2 and not head_distinct[1]):
      raise ParsingException('Can not parse rule head. Something is wrong with '
                             'how >>distinct<< is used.', head)
    parsed_head_call, is_distinct = ParseHeadCall(head_distinct[0])
    result = {'head': parsed_head_call,
              'distinct_denoted': True}
  if len(parts) == 2:
    body = parts[1]
    result['body'] = {'conjunction': ParseConjunction(body,
                                                      allow_singleton=True)}
  result['full_text'] = s  # For error messages.
  return result


##################################
# Parsing the file and imports.
#


def SplitImport(import_str):
  """Splitting import statement into (path, predicate, synonym)."""
  # TODO: It's not ideal to rely on percise spaces.
  import_path_synonym = Split(import_str, ' as ')
  if len(import_path_synonym) > 2:
    raise ParsingException('Too many "as":' % import_str,
                           HeritageAwareString(import_str))
  import_path = import_path_synonym[0]
  if len(import_path_synonym) == 2:
    synonym = import_path_synonym[1]
  else:
    synonym = None
  import_parts = import_path.split('.')
  assert import_parts[-1][0].upper() == import_parts[-1][0], (
      'One import per predicate please. Violator: %s', import_str)
  return ('.'.join(import_parts[:-1]), import_parts[-1], synonym)


def ParseImport(file_import_str, parsed_imports, import_chain, import_root):
  """Parses an import, returns extracted rules."""
  file_import_parts = file_import_str.split('.')
  if file_import_str in parsed_imports:
    if parsed_imports[file_import_str] is None:
      raise ParsingException(
          'Circular imports are not allowed: %s.' % '->'.join(import_chain +
                                                             [file_import_str]),
          HeritageAwareString(file_import_str))    
    return None
  parsed_imports[file_import_str] = None
  if isinstance(import_root, str):
    file_path = os.path.join(import_root, '/'.join(file_import_parts) + '.l')
    if not os.path.exists(file_path):
      raise ParsingException(
          'Imported file not found: %s.' % file_path,
          HeritageAwareString(
              'import ' + file_import_str + '.<PREDICATE>')[7:-11])
  else:
    assert isinstance(import_root, list), 'import_root must be of type str or list.'
    considered_files = []
    for root in import_root:
      file_path = os.path.join(root, '/'.join(file_import_parts) + '.l')
      considered_files.append(file_path)
      if os.path.exists(file_path):
        break
    else:
      raise ParsingException(
          'Imported file not found. Considered: \n- %s.' % '\n- '.join(
              considered_files),
          HeritageAwareString(
              'import ' + file_import_str + '.<PREDICATE>')[7:-11])

  with open(file_path) as f:
    file_content = f.read()
  parsed_file = ParseFile(file_content, file_import_str, parsed_imports,
                          import_chain, import_root)
  parsed_imports[file_import_str] = parsed_file
  return parsed_file


def DefinedPredicatesRules(rules):
  result = {}
  for r in rules:
    name = r['head']['predicate_name']
    defining_rules = result.get(name, [])
    defining_rules.append(r)
    result[name] = defining_rules
  return result


def MadePredicatesRules(rules):
  result = {}
  for r in rules:
    if '@Make' == r['head']['predicate_name']:
      name = r['head']['record']['field_value'][0]['value'][
          'expression']['literal']['the_predicate']['predicate_name']
      result[name] = r
  return result


def DefinedPredicates(rules):
  return set(DefinedPredicatesRules(rules))


def MadePredicates(rules):
  return set(MadePredicatesRules(rules))


def RenamePredicate(e, old_name, new_name):
  """Renames predicate in a syntax tree."""
  renames_count = 0
  if isinstance(e, dict):
    if 'predicate_name' in e and e['predicate_name'] == old_name:
      e['predicate_name'] = new_name
      renames_count += 1
    # Field names are treated as predicate names for functors.
    if 'field' in e and e['field'] == old_name:
      e['field'] = new_name
      renames_count += 1
  if isinstance(e, dict):
    for k in e:
      if isinstance(e[k], dict) or isinstance(e[k], list):
        renames_count += RenamePredicate(e[k], old_name, new_name)
  if isinstance(e, list):
    for idx in range(len(e)):
      if isinstance(e[idx], dict) or isinstance(e[idx], list):
        renames_count += RenamePredicate(e[idx], old_name, new_name)
  return renames_count


class MultiBodyAggregation(object):
  """This is a namespace for multi-body-aggregation processing functions."""

  SUFFIX = '_MultBodyAggAux'

  @classmethod
  def Rewrite(cls, rules):
    """Enabling multi-body-aggregation via auxiliary predicates."""
    rules = copy.deepcopy(rules)
    new_rules = []
    defined_predicates_rules = DefinedPredicatesRules(rules)
    multi_body_aggregating_predicates = [
        n for n, rs in defined_predicates_rules.items()
        if len(rs) > 1 and 'distinct_denoted' in rs[0]]
    aggregation_field_values_per_predicate = {}
    original_full_text_per_predicate = {}
    for rule in rules:
      name = rule['head']['predicate_name']
      original_full_text_per_predicate[name] = rule['full_text']
      if name in multi_body_aggregating_predicates:
        aggregation, new_rule = cls.SplitAggregation(rule)
        if name in aggregation_field_values_per_predicate:
          expected_aggregation = aggregation_field_values_per_predicate[name]
          if expected_aggregation != aggregation:
            raise ParsingException(
                'Signature differs for bodies of >>%s<<. '
                'Signatures observed: >>%s<<' % (name,
                                                 str((expected_aggregation,
                                                      aggregation))),
                HeritageAwareString(rule['full_text']))
        else:
          aggregation_field_values_per_predicate[name] = aggregation
        new_rules.append(new_rule)
      else:
        new_rules.append(rule)
    for name in multi_body_aggregating_predicates:
      pass_field_values = [
          {
              'field': f_v['field'],
              'value': {
                  'expression': {
                      'variable': {
                          'var_name': f_v['field']
                      }
                  }
              }
          }
          for f_v in aggregation_field_values_per_predicate[name]]
      aggregating_rule = {
          'head': {
              'predicate_name': name,
              'record': {
                  'field_value': aggregation_field_values_per_predicate[name]
              }
          },
          'body': {
              'conjunction': {
                  'conjunct': [{
                      'predicate': {
                          'predicate_name': name + cls.SUFFIX,
                          'record': {
                              'field_value': pass_field_values
                          }
                      }
                  }]
              }
          },
          'full_text': original_full_text_per_predicate[name],
          'distinct_denoted': True
      }
      new_rules.append(aggregating_rule)
    return new_rules

  @classmethod
  def SplitAggregation(cls, rule):
    """Replacing aggregations with their arguments."""
    rule = copy.deepcopy(rule)
    if 'distinct_denoted' not in rule:
      raise ParsingException('Inconsistency in >>distinct<< denoting for '
                             'predicate >>%s<<.' %
                             rule['head']['predicate_name'],
                             rule['full_text'])
    del rule['distinct_denoted']
    rule['head']['predicate_name'] = (
        rule['head']['predicate_name'] + cls.SUFFIX)
    transformation_field_values = []
    aggregation_field_values = []
    for field_value in rule['head']['record']['field_value']:
      if 'aggregation' in field_value['value']:
        aggregation_field_value = {
            'field': field_value['field'],
            'value': {
                'aggregation': {
                    'operator': field_value['value']['aggregation']['operator'],
                    'argument': {
                        'variable': {
                            'var_name': field_value['field']
                        }
                    }
                }
            }
        }
        new_field_value = {}
        new_field_value['field'] = field_value['field']
        new_field_value['value'] = {
            'expression': field_value['value']['aggregation']['argument']
        }
        transformation_field_values.append(new_field_value)
        aggregation_field_values.append(aggregation_field_value)
      else:
        aggregation_field_value = {
            'field': field_value['field'],
            'value': {
                'expression': {
                    'variable': {
                        'var_name': field_value['field']
                    }
                }
            }
        }
        aggregation_field_values.append(aggregation_field_value)
        transformation_field_values.append(field_value)
    rule['head']['record']['field_value'] = transformation_field_values
    return (aggregation_field_values, rule)


class DisjunctiveNormalForm(object):
  """This is namespace for transforming rules to DNF."""

  @classmethod
  def ConjunctionOfDnfs(cls, dnfs):
    """Returning DNF which is a conjunction of given DNFs."""
    if len(dnfs) == 1:
      return dnfs[0]

    result = []
    first_dnf = dnfs[0]
    other_dnfs = dnfs[1:]

    for a in first_dnf:
      for b in cls.ConjunctionOfDnfs(other_dnfs):
        result.append(a + b)
    return result

  @classmethod
  def ConjunctsToDNF(cls, conjuncts: List[Dict]) -> List[List[Dict]]:
    dnfs = list(map(cls.PropositionToDNF, conjuncts))
    result = cls.ConjunctionOfDnfs(dnfs)

    return result

  @classmethod
  def DisjunctsToDNF(cls, disjuncts: List[Dict]) -> List[List[Dict]]:
    dnfs = list(map(cls.PropositionToDNF, disjuncts))
    result = []
    for d in dnfs:
      result += d
    return result

  @classmethod
  def PropositionToDNF(cls, proposition):
    if 'conjunction' in proposition:
      return cls.ConjunctsToDNF(proposition['conjunction']['conjunct'])
    if 'disjunction' in proposition:
      return cls.DisjunctsToDNF(proposition['disjunction']['disjunct'])
    return [[proposition]]

  @classmethod
  def RuleToRules(cls, rule):
    """Eliminating disjunction in the rule via DNF rewrite."""
    if 'body' not in rule:
      return [rule]
    proposition = rule['body']
    dnf = cls.PropositionToDNF(proposition)
    result = []
    for conjuncts in dnf:
      new_rule = copy.deepcopy(rule)
      new_rule['body']['conjunction']['conjunct'] = copy.deepcopy(conjuncts)
      result.append(new_rule)
    return result

  @classmethod
  def Rewrite(cls, rules):
    result = []
    for rule in rules:
      result.extend(cls.RuleToRules(rule))
    return result


class AggergationsAsExpressions(object):
  """Namespace for rewriting aggregation internals as expressions."""

  @classmethod
  def AggregationOperator(cls, raw_operator):
    if raw_operator == '+':
      return 'Agg+'
    if raw_operator == '++':
      return 'Agg++'
    return raw_operator

  @classmethod
  def Convert(cls, a):
    return {
        'call': {
            'predicate_name': cls.AggregationOperator(a['operator']),
            'record': {
                'field_value': [
                    {
                        'field': 0,
                        'value': {
                            'expression': a['argument']
                        }
                    }
                ]
            }
        }
    }

  @classmethod
  def RewriteInternal(cls, s):
    """Replacing aggregation operator and argument with an expression."""
    if isinstance(s, dict):
      member_index = sorted(s.keys())
    elif isinstance(s, list):
      member_index = list(range(len(s)))
    else:
      assert False, 'Rewrite should be called on list or dict. Got: %s' % str(s)

    for k in member_index:
      if (isinstance(s[k], dict) and
          'aggregation' in s[k]):
        a = s[k]['aggregation']
        a['expression'] = cls.Convert(a)
        del a['operator']
        del a['argument']

    if isinstance(s, dict) or isinstance(s, list):
      for k in member_index:
        if isinstance(s[k], dict) or isinstance(s[k], list):
          cls.RewriteInternal(s[k])

  @classmethod
  def Rewrite(cls, rules):
    rules = copy.deepcopy(rules)
    cls.RewriteInternal(rules)
    return rules


def ParseFile(s, this_file_name=None, parsed_imports=None, import_chain=None,
              import_root=None):
  """Parsing logica.Logica."""
  s = HeritageAwareString(RemoveComments(HeritageAwareString(s)))
  parsed_imports = parsed_imports or {}
  this_file_name = this_file_name or 'main'
  import_chain = import_chain or []
  import_chain = import_chain + [this_file_name]
  import_root = import_root or ''
  str_statements = Split(s, ';')
  rules = []
  imported_predicates = []
  predicates_created_by_import = {}
  for str_statement in str_statements:
    if not str_statement:
      continue
    if str_statement.startswith('import '):
      import_str = str_statement[len('import '):]
      file_import_str, import_predicate, synonym = SplitImport(import_str)
      ParseImport(file_import_str, parsed_imports, import_chain,
                  import_root)
      imported_predicates.append({
          'file': file_import_str, 'predicate_name': import_predicate,
          'synonym': synonym})
      if file_import_str not in predicates_created_by_import:
        predicates_created_by_import[file_import_str] = (
            DefinedPredicates(parsed_imports[file_import_str]['rule']) |
            MadePredicates(parsed_imports[file_import_str]['rule']))
      continue

    rule = None
    annotation_and_rule = ParseFunctionRule(HeritageAwareString(str_statement))
    if annotation_and_rule:
      annotation, rule = annotation_and_rule
      rules.append(annotation)
    if not rule:
      rule = ParseFunctorRule(HeritageAwareString(str_statement))
    if not rule:
      rule = ParseRule(HeritageAwareString(str_statement))

    if rule:
      rules.append(rule)
  # Eliminate explicit disjunctions via DNF reduction.
  rules = DisjunctiveNormalForm.Rewrite(rules)
  # Multibody aggregation uses concise aggregation structure.
  rules = MultiBodyAggregation.Rewrite(rules)
  # Concise structure is no longer needed, rewriting into expressions.
  rules = AggergationsAsExpressions.Rewrite(rules)

  # Building a unique among already parsed imports prefix.
  if this_file_name == 'main':
    this_file_prefix = ''
  else:
    existing_prefixes = set()

    for some_parsed_import in parsed_imports.values():
      if some_parsed_import:
        assert some_parsed_import[
            'predicates_prefix'] not in existing_prefixes
        existing_prefixes.add(some_parsed_import['predicates_prefix'])
    parts = this_file_name.split('.')
    idx = -1
    this_file_prefix = parts[idx] + '_'
    while this_file_prefix in existing_prefixes:
      idx -= 1
      assert idx > 0, (
          'It looks like some of import paths are equal modulo '
          'symbols _ and /. This confuses me: %s' % this_file_prefix)
      this_file_prefix = parts[idx] + this_file_prefix

  # Renaming predicates, adding file prefix to them.
  if this_file_name != 'main':
    for p in DefinedPredicates(rules) | MadePredicates(rules):
      if p[0] != '@' and p != '++?':
        RenamePredicate(rules, p, this_file_prefix + p)
  for s in imported_predicates:
    imported_predicate_file = s['file']
    import_prefix = parsed_imports[
        imported_predicate_file]['predicates_prefix']
    assert import_prefix, (
        'Empty import prefix: %s -> %s' % (
            imported_predicate_file,
            parsed_imports[imported_predicate_file]))
    imported_predicate_name = s['predicate_name']
    predicate_imported_as = s['synonym'] or imported_predicate_name
    rename_count = RenamePredicate(rules,
                                   predicate_imported_as,
                                   import_prefix + imported_predicate_name)
    if (import_prefix +
        imported_predicate_name) not in predicates_created_by_import[
            imported_predicate_file]:
      raise ParsingException(
          'Predicate %s from file %s is imported by %s, but is not defined.' % (
              imported_predicate_name, imported_predicate_file,
              this_file_name),
          HeritageAwareString(
              imported_predicate_file + ' -> ' + imported_predicate_name))

    if not rename_count:
      raise ParsingException(
          'Predicate %s from file %s is imported by %s, but not used.' % (
              imported_predicate_name, imported_predicate_file,
              this_file_name),
          HeritageAwareString(
              imported_predicate_file + ' -> ' + predicate_imported_as))

  # If this is main file, then it's time to assemble all the rules together.
  if this_file_name == 'main':
    defined_predicates = DefinedPredicates(rules)
    main_defined_predicates = copy.deepcopy(defined_predicates)
    for i in parsed_imports.values():
      new_predicates = DefinedPredicates(i['rule'])
      if any(p[0] != '@' for p in defined_predicates & new_predicates):
        raise ParsingException(
            'Predicate from file {0} is overridden by some importer.'.format(
                i['file_name']), HeritageAwareString(
                    str(defined_predicates & new_predicates)))
      defined_predicates |= new_predicates
      rules.extend(i['rule'])

  # Uncomment to debug:
  # pprint.pprint(rules, stream=sys.stderr)
  return {'rule': rules,
          'imported_predicates': imported_predicates,
          'predicates_prefix': this_file_prefix,
          'file_name': this_file_name}
