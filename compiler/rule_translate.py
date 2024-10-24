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

"""Compiler of a single Logica rule to SQL."""

import collections
import copy
import string
import sys

if '.' not in __package__:
  from common import color
  from compiler import expr_translate
else:
  from ..common import color
  from ..compiler import expr_translate

xrange = range

def Indent2(s):
  return '\n'.join('  ' + l for l in s.split('\n'))


LogicalVariable = collections.namedtuple(
  'LogicalVariable',
  [
    'variable_name',    # Name of user or generated variable.
    'predicate_name',   # Name of a predicate in rule for which the variable is
                        # used.
    'is_user_variable'  # Whether this is a user variable (vs generated one).
  ])


class RuleCompileException(Exception):
  """Exception thrown when user-error is detected at rule-compile time."""

  def __init__(self, message, rule_str):
    super(RuleCompileException, self).__init__(message)
    self.rule_str = rule_str

  def ShowMessage(self, stream=sys.stderr):
    print(color.Format('{underline}Compiling{end}:'), file=stream)
    print(self.rule_str, file=stream)
    print(color.Format('\n[ {error}Error{end} ] ') + str(self), file=stream)


def LogicaFieldToSqlField(logica_field):
  if isinstance(logica_field, int):
    # TODO: Ensure that no collision occurs.
    return 'col%d' % logica_field
  return logica_field


def HeadToSelect(head):
  """Converting a rule head to a SELECT representation."""
  select = collections.OrderedDict()
  aggregated_vars = []
  for field_value in head['record']['field_value']:
    k = field_value['field']
    v = field_value['value']
    if 'aggregation' in v:
      select[k] = copy.deepcopy(v['aggregation']['expression'])
      aggregated_vars.append(k)
    else:
      assert 'expression' in v, 'Bad select value: %s' % str(v)
      select[k] = v['expression']  # <=> v as k
  # Allowing predicates with no arguments.
  if not select:
    select['atom'] = {'literal': {'the_string': {'the_string': 'yes'}}}

  return (select, aggregated_vars)


def AllMentionedVariables(x, dive_in_combines=False, this_is_select=False):
  """Extracting all variables mentioned in an expression."""
  r = []
  # In select there can be a variable named variable.
  if isinstance(x, dict) and 'variable' in x and not this_is_select:
    r.append(x['variable']['var_name'])
  if isinstance(x, list):
    for v in x:
      r.extend(AllMentionedVariables(v, dive_in_combines))
  if isinstance(x, dict):
    for k in x:
      # Variables mentioned in 'combine' expression may be resolved via tables
      # of the 'combine' expression. So they are not to be included in the
      # parent query.
      if k != 'combine' or dive_in_combines:
        r.extend(AllMentionedVariables(x[k], dive_in_combines))
  return set(r)


def ReplaceVariable(old_var, new_expr, s):
  """Replacing a variable in expressoin s."""
  if isinstance(s, dict):
    member_index = sorted(s.keys(), key=str)
  elif isinstance(s, list):
    member_index = range(len(s))
  else:
    assert False, 'Replace should be called on list or dict. Got: %s' % str(s)

  for k in member_index:
    if (isinstance(s[k], dict) and
        'variable' in s[k] and
        s[k]['variable']['var_name'] == old_var):
      s[k] = new_expr
  if isinstance(s, dict):
    for k in s:
      if isinstance(s[k], dict) or isinstance(s[k], list):
        ReplaceVariable(old_var, new_expr, s[k])
  if isinstance(s, list):
    for k in s:
      if isinstance(k, dict) or isinstance(k, list):
        ReplaceVariable(old_var, new_expr, k)


class NamesAllocator(object):
  """Allocator of unique names for tables and variables.

  Also holds existing built-in function names.
  """

  def __init__(self, custom_udfs=None):
    self.aux_var_num = 0
    self.table_num = 0
    self.allocated_tables = set()
    self.custom_udfs = custom_udfs or {}

  def AllocateVar(self, hint=None):
    v = 'x_%d' % self.aux_var_num
    self.aux_var_num += 1
    return v

  def AllocateTable(self, hint_for_user=None):
    """Allocating a table name."""
    allowed_chars = set(string.ascii_letters + string.digits + '_./')
    if hint_for_user and len(hint_for_user) < 100:
      suffix = ''.join(
          ('_' if c in ['.', '/'] else c)
          for c in hint_for_user if c in allowed_chars)
    else:
      suffix = ''
    if suffix and suffix not in self.allocated_tables:
      t = suffix
    else:
      if suffix:
        suffix = '_' + suffix
      t = 't_%d%s' % (self.table_num, suffix)
      self.table_num += 1
    self.allocated_tables.add(t)
    return t

  def FunctionExists(self, function_name):
    return (function_name in expr_translate.QL.BasisFunctions() or
            function_name in self.custom_udfs)


class ExceptExpression(object):
  """Namespace for constructing and recognizing 'Except' expressions."""

  @classmethod
  def Build(cls, table_name, except_fields):
    return '(SELECT AS STRUCT %s.* EXCEPT (%s))' % (table_name,
                                                    ','.join(except_fields))

  @classmethod
  def Recognize(cls, field_name):
    # Only 'Except' variables start with "(SELECT AS STRUCT".
    return field_name.startswith('(SELECT AS STRUCT')


class RuleStructure(object):
  """Representing a single Logica rule structure.

  Can convert itself into an SQL SELECT statement.
  """

  def __init__(self, names_allocator=None, external_vocabulary=None,
               custom_udfs=None):
    # Name of this predicate.
    self.this_predicate_name = ''
    # Table name to table predicate.
    self.tables = collections.OrderedDict()
    # Table variable to clause variable map.
    self.vars_map = {}
    # Clause variable to one table variable.
    self.inv_vars_map = {}
    self.vars_unification = []
    self.constraints = []
    self.select = collections.OrderedDict()
    self.unnestings = []
    self.distinct_vars = []
    names_allocator = names_allocator or NamesAllocator(custom_udfs=custom_udfs)
    self.allocator = names_allocator
    self.external_vocabulary = external_vocabulary
    self.synonym_log = {}
    self.full_rule_text = None
    self.distinct_denoted = None

  def SelectAsRecord(self):
    def StrIntKey(x):
      k, v = x
      if isinstance(k, str):
        return (k, v)
      if isinstance(k, int):
        return ('%03d' % k, v)
      assert False, 'x:%s' % str(x)    
    return {'record': {
      'field_value': [{
        'field': k,
        'value': {'expression': v}
      } for k, v in sorted(self.select.items(), key=StrIntKey)]}}

  def OwnVarsVocabulary(self):
    """Returns a map: logica variable -> SQL expression with the value."""
    def TableAndFieldToSql(table, field):
      if ExceptExpression.Recognize(field):
        return field
      elif table and field != '*':
        return '%s.%s' % (table, field)
      elif not table:
        return field
      else:  # field == '*'
        return table
    return {k: TableAndFieldToSql(v[0], LogicaFieldToSqlField(v[1]))
            for k, v in self.inv_vars_map.items()}

  def VarsVocabulary(self):
    r = {}
    r.update(self.OwnVarsVocabulary())
    if self.external_vocabulary:
      r.update(self.external_vocabulary)
    return r

  def ExtractedVariables(self):
    return set(self.VarsVocabulary().keys())

  def InternalVariables(self):
    return self.AllVariables() - self.ExtractedVariables()

  def AllVariables(self):
    r = set()
    r |= AllMentionedVariables(self.select, this_is_select=True)
    r |= AllMentionedVariables(self.vars_unification)
    r |= AllMentionedVariables(self.constraints)
    r |= AllMentionedVariables(self.unnestings)
    return r

  def SortUnnestings(self):
    """Sorts unnestings in dependency order."""
    unnesting_of = {u[0]['variable']['var_name']: u
                    for u in self.unnestings}
    unnesting_variables = set(unnesting_of)
    depends_on = {u[0]['variable']['var_name']:
                      set(AllMentionedVariables(u[1], dive_in_combines=True)) &
                      unnesting_variables for u in self.unnestings}

    unnested = set()
    ordered_unnestings = []
    while unnesting_of:
      for v, u in sorted(unnesting_of.items()):
        if depends_on[v] <= unnested:
          ordered_unnestings.append(unnesting_of[v])
          del unnesting_of[v]
          unnested.add(v)
          break
      else:
        raise RuleCompileException(
            color.Format(
                'There seem to be a circular dependency of {warning}In{end} '
                'calls. '
                'This error might also come from injected sub-rules.'),
            self.full_rule_text)
    self.unnestings = ordered_unnestings

  def ReplaceVariableEverywhere(self, u_left, u_right):
    if 'variable' in u_right:
      l = self.synonym_log.get(u_right['variable']['var_name'], [])
      l.append(LogicalVariable(variable_name=u_left,
                               predicate_name=self.this_predicate_name,
                               # TODO: sqlite_recursion somehow gets
                               # u_left to be int. 
                               is_user_variable=(isinstance(u_left, str) and
                                                 not u_left.startswith('x_'))))
      l.extend(self.synonym_log.get(u_left, []))
      self.synonym_log[u_right['variable']['var_name']] = l
    ReplaceVariable(u_left, u_right, self.unnestings)
    ReplaceVariable(u_left, u_right, self.select)
    ReplaceVariable(u_left, u_right, self.vars_unification)
    ReplaceVariable(u_left, u_right, self.constraints)
    
  # TODO: Parameter unfold_recods just patches some bug. Careful review is needed.
  def ElliminateInternalVariables(self, assert_full_ellimination=False, unfold_records=True):
    """Elliminates internal variables via substitution."""
    variables = self.InternalVariables()
    while True:
      done = True
      self.vars_unification = [
          u for u in self.vars_unification if u['left'] != u['right']]
      for u in self.vars_unification:
        # Direct variable assignments.
        for k, r in [['left', 'right'], ['right', 'left']]:
          if u[k] == u[r]:
            continue
          ur_variables = AllMentionedVariables(u[r])
          ur_variables_incl_combines = AllMentionedVariables(
              u[r], dive_in_combines=True)
          if (isinstance(u[k], dict) and
              'variable' in u[k] and
              u[k]['variable']['var_name'] in variables and
              u[k]['variable']['var_name'] not in ur_variables_incl_combines and
              (
                  ur_variables <= self.ExtractedVariables() or
                  not str(u[k]['variable']['var_name']).startswith('x_'))):
            u_left = u[k]['variable']['var_name']
            u_right = u[r]
            self.ReplaceVariableEverywhere(u_left, u_right)
            done = False
        # Assignments to variables in record fields.
        if unfold_records:  # Confirm that unwraping works and make this unconditional.
          # Unwrapping goes wild sometimes. Letting it go right to left only.
          # for k, r in [['left', 'right']]:
          for k, r in [['left', 'right'], ['right', 'left']]:
            if u[k] == u[r]:
              continue
            ur_variables = AllMentionedVariables(u[r])
            ur_variables_incl_combines = AllMentionedVariables(
                u[r], dive_in_combines=True)
            if (isinstance(u[k], dict) and
                'record' in u[k] and
                ur_variables <= self.ExtractedVariables()):
              def AssignToRecord(target, source):
                global done
                for fv in target['record']['field_value']:
                  def MakeNewSource():
                    return {
                      'subscript': {
                        'record': source,
                        'subscript': {'literal': {'the_symbol': {'symbol': fv['field']}}}
                      }
                    }
                  if ('variable' in fv['value']['expression'] and
                      fv['value']['expression']['variable']['var_name']
                        in variables and
                      fv['value']['expression']['variable']['var_name']
                        not in ur_variables_incl_combines):
                    u_left = fv['value']['expression']['variable']['var_name']
                    u_right = MakeNewSource()
                    self.ReplaceVariableEverywhere(u_left, u_right)
                    done = False
                  if 'record' in fv['value']['expression']:
                    new_target = fv['value']['expression']
                    new_source = MakeNewSource()
                    AssignToRecord(new_target, new_source)

              AssignToRecord(u[k], u[r])
      
      if done:
        variables = self.InternalVariables()
        if assert_full_ellimination:
          if True:
            if variables:
              violators = []
              for v in variables:
                violators.extend(
                  v.variable_name 
                  for v in self.synonym_log.get(v, [])
                  if v.predicate_name == self.this_predicate_name)
                violators.append(v)
              violators = {v for v in violators if not v.startswith('x_')}
              # Remove disambiguation suffixes from variables not to confuse
              # the user.
              if violators:
                violators = {v.split(' # disambiguated')[0] for v in violators}
                raise RuleCompileException(
                    color.Format(
                        'Found no way to assign variables: '
                        '{warning}{violators}{end}.',
                        dict(violators=', '.join(sorted(violators)))),
                    self.full_rule_text)
              else:
                user_variables = [
                  uv for v in variables 
                  for uv in self.synonym_log.get(v, [])
                  if uv.is_user_variable]
                this_predicate = color.Format('{warning}{p}{end}',
                                              dict(p=self.this_predicate_name))
                unassigned_vars = ', '.join(
                  color.Format('{warning}{var}{end} in rule for '
                               '{warning}{p}{end}',
                               dict(var=v.variable_name, p=v.predicate_name))
                  for v in user_variables
                )
                assert user_variables, (
                    'Logica needs better error messages: purely internal '
                    'variable was not eliminated. It looks like you have '
                    'not passed a required argument to some called predicate. '
                    'Use --add_debug_info_to_var_names flag to make this message '
                    'a little more informatvie. '
                    'Variables: %s, synonym_log: %s' % (str(variables),
                                                        str(self.synonym_log)))
                raise RuleCompileException(
                  'While compiling predicate ' + this_predicate + ' there was '
                  'found no way to assign variables: ' + unassigned_vars + '.',
                  self.full_rule_text)
          else:
            assert not variables, (
                'Not all internal variables were eliminated. Violators:\n' +
                ',\n'.join(
                    '%s (aka %s)' % (v, self.synonym_log[v])
                    for v in variables) +
                '\nRule: %s' % self)
        else:
          unassigned_variables = []
          for v in variables:
            if not v.startswith('x_'):
              unassigned_variables.append(v)
          # Remove disambiguation suffixes from variables not to confuse
          # the user.
          unassigned_variables = {v.split(' # disambiguated')[0]
                                  for v in unassigned_variables}
          if unassigned_variables:
            raise RuleCompileException(
                color.Format(
                    'Found no way to assign variables: '
                    '{warning}{violators}{end}. '
                    'This error might also come from injected sub-rules.',
                    dict(violators=', '.join(sorted(unassigned_variables)))),
                self.full_rule_text)
        break

  def __str__(self):
    return ('%s ==> \n'
            'tables = %s,\n '
            'vars_map = %s,\n '
            'vars_unification = %s,\n '
            'external_vocabulary = %s,\n '
            'constraints = %s,\n '
            'select = %s,\n '
            'unnest = %s' % (
                self.this_predicate_name,
                self.tables, self.vars_map, self.vars_unification,
                self.external_vocabulary,
                self.constraints, self.select, self.unnestings))

  def UnificationsToConstraints(self):
    for u in self.vars_unification:
      if u['left'] == u['right']:
        continue
      self.constraints.append({
          'call': {
              'predicate_name': '==',
              'record': {
                  'field_value': [{
                      'field': 'left',
                      'value': {
                          'expression': u['left']
                      }
                  }, {
                      'field': 'right',
                      'value': {
                          'expression': u['right']
                      }
                  }]
              }
          }
      })

  def AsSql(self, subquery_encoder=None, flag_values=None):
    """Outputing SQL representing this structure."""
    # pylint: disable=g-long-lambda
    ql = expr_translate.QL(self.VarsVocabulary(), subquery_encoder,
                           lambda message:
                           RuleCompileException(message, self.full_rule_text),
                           flag_values,
                           custom_udfs=subquery_encoder.execution.custom_udfs,
                           dialect=subquery_encoder.execution.dialect)
    r = 'SELECT\n'
    fields = []
    if not self.select:
      raise RuleCompileException(
          color.Format(
              'Tables with {warning}no columns{end} are not allowed in '
              'StandardSQL, so they are not allowed in Logica.'),
          self.full_rule_text)

    for k, v in self.select.items():
      if k == '*':
        if 'variable' in v:
          v['variable']['dont_expand'] = True  # For SQLite.
        fields.append(
          subquery_encoder.execution.dialect.Subscript(
           ql.ConvertToSql(v), '*', True))
      else:
        fields.append('%s AS %s' % (ql.ConvertToSql(v), LogicaFieldToSqlField(k)))
    r += ',\n'.join('  ' + f for f in fields)
    if (self.tables or self.unnestings or
        self.constraints or self.distinct_denoted):
      r += '\nFROM\n'
      tables = []
      for k, v in self.tables.items():
        if subquery_encoder:
          # Note that we are passing external_vocabulary, not VarsVocabulary
          # here. I.e. if this is a sub-query then variables of outer tables
          # can be used.
          sql = subquery_encoder.TranslateTable(v, self.external_vocabulary)
          if not sql:
            raise RuleCompileException(
                color.Format(
                    'Rule uses table {warning}{table}{end}, which is not '
                    'defined. External tables can not be used in '
                    '{warning}\'testrun\'{end} mode. This error may come '
                    'from injected sub-rules.',
                    dict(table=v)), self.full_rule_text)
        if sql != k:
          tables.append(sql + ' AS ' + k)
        else:
          tables.append(sql)
      self.SortUnnestings()
      for element, the_list in self.unnestings:
        if 'variable' in element:
          # To prevent SQLite record unfolding.
          element['variable']['dont_expand'] = True
        tables.append(
            subquery_encoder.execution.dialect.UnnestPhrase().format(
                ql.ConvertToSql(the_list), ql.ConvertToSql(element)))
      if not tables:
        tables.append("(SELECT 'singleton' as s) as unused_singleton")
      from_str = ', '.join(tables)
      # Indent the from_str.
      from_str = '\n'.join('  ' + l for l in from_str.split('\n'))
      r += from_str
      if self.constraints:
        constraints = []
        # Predicates used for type inference.
        ephemeral_predicates = ['~']
        for c in self.constraints:
          if c['call']['predicate_name'] not in ephemeral_predicates:
            constraints.append(ql.ConvertToSql(c))
        if constraints:
          r += '\nWHERE\n'
          r += ' AND\n'.join(map(Indent2, constraints))
      if self.distinct_vars:
        ordered_distinct_vars = [
            v for v in self.select.keys() if v in self.distinct_vars]
        r += '\nGROUP BY '
        if subquery_encoder.execution.dialect.GroupBySpecBy() == 'name':
          r += ', '.join(map(LogicaFieldToSqlField, ordered_distinct_vars))
        elif subquery_encoder.execution.dialect.GroupBySpecBy() == 'index':
          selected_fields = list(self.select.keys())
          r += ', '.join(str(selected_fields.index(v) + 1)
                         for v in ordered_distinct_vars)
        elif subquery_encoder.execution.dialect.GroupBySpecBy() == 'expr':
          r += ', '.join(
            ql.ConvertToSqlForGroupBy(self.select[k])
            for k in ordered_distinct_vars
          )
        else:
          assert False, 'Broken dialect %s, group by spec: %s' % (
              subquery_encoder.execution.dialect.Name(),
              subquery_encoder.execution.dialect.GroupBySpecBy())

    return r


def ExtractPredicateStructure(c, s):
  """Updating RuleStructure s with a predicate call."""
  predicate = c['predicate_name']

  if predicate in (
      '<=', '<', '>', '>=', '!=', '&&', '||', '!', 'IsNull', 'Like',
      'Constraint', 'is', 'is not', '~'):
    s.constraints.append({'call': c})
    return

  table_name = s.allocator.AllocateTable(predicate)
  s.tables[table_name] = predicate
  for field_value in c['record']['field_value']:
    assert 'field' in field_value, ('Corrupt record: %s' % c['record'])
    if 'except' in field_value:
      table_var = ExceptExpression.Build(table_name, field_value['except'])
    else:
      table_var = field_value['field']
    expr = field_value['value']['expression']
    var_name = s.allocator.AllocateVar('%s_%s' % (table_name, table_var))
    s.vars_map[table_name, table_var] = var_name
    s.inv_vars_map[var_name] = (table_name, table_var)
    s.vars_unification.append(
        {
            'left': {'variable': {'var_name': var_name}},
            'right': expr
        })


def ExtractInclusionStructure(inclusion, s):
  """Updating RuleStructure s with an inclusion."""
  # Handling inclusion as a WHERE constraint.
  if 'call' in inclusion['list']:
    if inclusion['list']['call']['predicate_name'] == 'Container':
      s.constraints.append({
          'call': {
              'predicate_name': 'In',
              'record': {
                  'field_value': [
                      {
                          'field': 'left',
                          'value': {'expression': inclusion['element']}
                      },
                      {
                          'field': 'right',
                          'value': {'expression': inclusion['list']}
                      }
                  ]
              }
          }
      })
      return
  # Handling inclusion as an UNNEST.
  var_name = s.allocator.AllocateVar('unnest_`%s`' % inclusion['element'])
  s.vars_map[None, var_name] = var_name
  s.inv_vars_map[var_name] = (None, var_name)
  s.unnestings.append([{'variable': {'var_name': var_name}}, inclusion['list']])
  s.vars_unification.append({
      'left': inclusion['element'],
      'right': {
        'call': {
          'predicate_name': 'ValueOfUnnested',
          'record': {
            'field_value': [{
              'field': 0,
              'value': {
                'expression': {
                  'variable': {
                    'var_name': var_name,
                    'dont_expand': True
                  }
                }
              }
            }]
          }
        }
      }
  })


def ExtractConjunctiveStructure(conjuncts, s):
  """Updates RuleStructure with the conjuncts."""
  for c in conjuncts:
    if 'predicate' in c:
      ExtractPredicateStructure(c['predicate'], s)
    elif 'unification' in c:
      if ('variable' in c['unification']['right_hand_side'] or
          'variable' in c['unification']['left_hand_side'] or
          'record' in c['unification']['left_hand_side'] or
          'record' in c['unification']['right_hand_side']):
        s.vars_unification.append({
            'left': c['unification']['left_hand_side'],
            'right': c['unification']['right_hand_side']})
      else:
        if (c['unification']['left_hand_side'] !=
            c['unification']['right_hand_side']):
          s.constraints.append({
              'call': {
                  'predicate_name': '==',
                  'record': {
                      'field_value': [
                          {
                              'field': 'left',
                              'value': {
                                  'expression':
                                      c['unification']['left_hand_side']
                              }
                          },
                          {
                              'field': 'right',
                              'value': {
                                  'expression':
                                      c['unification']['right_hand_side']
                              }
                          }
                      ]
                  }
              }
          })
    elif 'inclusion' in c:
      ExtractInclusionStructure(c['inclusion'], s)
    else:
      assert False, 'Unsupported conjunct: %s' % c


def HasCombine(r):
  """Whether structure involves Combine predicate."""
  if isinstance(r, dict):
    member_index = sorted(r.keys())
  elif isinstance(r, list):
    member_index = range(len(r))
  else:
    assert False, (
        'HasCombine should be called on list or dict. Got: %s' % str(r))

  if isinstance(r, dict):
    if 'predicate_name' in r and r['predicate_name'] == 'Combine':
      return True

  for k in member_index:
    if isinstance(r[k], dict) or isinstance(r[k], list):
      if HasCombine(r[k]):
        return True

  return False


def AllRecordFields(record):
  result = []
  for field_value in record['field_value']:
    result.append(field_value['field'])
  return result


def InlinePredicateValuesRecursively(r, names_allocator, conjuncts):
  """Replaces expression predicate calls with logica_value column."""
  if isinstance(r, dict):
    member_index = sorted(r.keys())
  elif isinstance(r, list):
    member_index = range(len(r))
  else:
    assert False, (
        'InlinePredicateValuesRecursively should be called on list or dict. '
        'Got: %s' % str(r))

  for k in member_index:
    if k != 'combine' and k != 'type':
      if isinstance(r[k], dict) or isinstance(r[k], list):
        InlinePredicateValuesRecursively(r[k], names_allocator, conjuncts)

  if isinstance(r, dict):
    if 'call' in r:
      if not names_allocator.FunctionExists(r['call']['predicate_name']):
        aux_var = names_allocator.AllocateVar('inline')
        r_predicate = {}
        r_predicate['predicate'] = copy.deepcopy(r['call'])
        r_predicate['predicate']['record']['field_value'].append({
            'field': 'logica_value',
            'value': {'expression': {'variable': {'var_name': aux_var}}}
        })
        del r['call']
        r['variable'] = {'var_name': aux_var}
        conjuncts.append(r_predicate)


def InlinePredicateValues(rule, names_allocator):
  extra_conjuncts = []
  InlinePredicateValuesRecursively(rule, names_allocator, extra_conjuncts)
  if extra_conjuncts:
    conjuncts = rule.get('body', {}).get('conjunction', {}).get('conjunct', [])
    conjuncts.extend(extra_conjuncts)
    rule['body'] = {'conjunction': {'conjunct': conjuncts}}


def GetTreeOfCombines(rule, tree=None):
  """Get the tree structure of combines in the rule syntax subtree."""
  if not tree:
    tree = {'rule': rule, 'variables': set(), 'subtrees': []}

  if isinstance(rule, list):
    for v in rule:
      tree = GetTreeOfCombines(v, tree)
  if isinstance(rule, dict):
    if 'variable' in rule:
      variables = tree['variables']
      variables.add(rule['variable']['var_name'])
    for k in rule:
      # Variables mentioned in 'combine' expression may be resolved via tables
      # of the 'combine' expression. So they are not to be included in the
      # parent query.
      if k != 'combine':
        tree = GetTreeOfCombines(rule[k], tree)
      else:
        subtree = GetTreeOfCombines(rule[k])
        subtrees = tree['subtrees']
        subtrees.append(subtree)
  return tree


def DisambiguateCombineVariables(rule, names_allocator):
  """Disambiguate variables in combine expressions.

  Variables of the same name in different combine statements are actually
  different. The same name becomes a problem if one combine statement is
  substituted into another when unifications are processed.

  This function appends a disambiguation suffix to all variables first
  mentioned in combine statements.

  Args:
    rule: A rule to process.
    names_allocator: An execution level allocator of variable names.
  """
  def Replace(tree, outer_variables):
    """Replace all variables with their disambiguated counterparts."""
    variables = tree['variables']
    introduced_variables = variables - outer_variables
    all_variables = variables | outer_variables
    for v in introduced_variables:
      if '# disambiguated with' in v:
        # This variable was already disambiguated.
        # We get here, when ExtractRuleStructure is called on the combine
        # expression itself.
        continue
      new_name = '%s # disambiguated with %s' % (
          v, names_allocator.AllocateVar('combine_dis'))
      ReplaceVariable(v, {'variable': {'var_name': new_name}}, tree['rule'])
    for s in tree['subtrees']:
      Replace(s, all_variables)

  tree = GetTreeOfCombines(rule)
  top_variables = tree['variables']
  for t in tree['subtrees']:
    Replace(t, top_variables)


def ExtractRuleStructure(rule, names_allocator=None, external_vocabulary=None):
  """Extracts RuleStructure from rule."""
  rule = copy.deepcopy(rule)
  # Not disambiguating if this rule is extracting structure of the combine
  # itself, as variables of this combine were already disambiguated from
  # parent rule.
  if rule['head']['predicate_name'] != 'Combine':
    DisambiguateCombineVariables(rule, names_allocator)
  s = RuleStructure(names_allocator, external_vocabulary)
  InlinePredicateValues(rule, names_allocator)
  s.full_rule_text = rule['full_text']
  s.this_predicate_name = rule['head']['predicate_name']
  (s.select, aggregated_vars) = HeadToSelect(rule['head'])
  # Adding internal variable unification with select arguments to avoid
  # confusion of user variables between injected predicates.
  for k, expr in s.select.items():
    if 'variable' in expr:
      s.vars_unification.append({
          'left': expr,
          'right': {'variable': {'var_name': names_allocator.AllocateVar(
              'extract_%s_%s' % (s.this_predicate_name, k))}}})
  if 'body' in rule:
    ExtractConjunctiveStructure(rule['body']['conjunction']['conjunct'], s)

  distinct_denoted = 'distinct_denoted' in rule
  s.distinct_denoted = distinct_denoted
  if aggregated_vars and not distinct_denoted:
    raise RuleCompileException(
        color.Format(
            'Aggregating predicate must be {warning}distinct{end} denoted.'),
        s.full_rule_text)
  if distinct_denoted:
    s.distinct_vars = sorted(
        list(set(s.select.keys()) - set(aggregated_vars)), key=str)
  return s
