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

import hashlib
import json
import sys

if '.' not in __package__:
  from type_inference.research import reference_algebra
  from type_inference.research import types_of_builtins
  from common import color
else:
  from ..research import reference_algebra
  from ..research import types_of_builtins
  try:
    from ...common import color
  except:
    from common import color


class ContextualizedError:
  def __init__(self):
    self.type_error = None
    self.context_string = None
    self.refers_to_variable = None
    self.refers_to_expression = None
  
  def Replace(self, type_error, context_string, refers_to_variable, refers_to_expression):
    self.type_error = type_error
    self.context_string = context_string
    self.refers_to_variable = refers_to_variable
    self.refers_to_expression = refers_to_expression

  def ReplaceIfMoreUseful(self, type_error, context_string, refers_to_variable, refers_to_expression):
    if self.type_error is None:
      self.Replace(type_error, context_string, refers_to_variable, refers_to_expression)
    if self.context_string == 'UNKNOWN LOCATION':
      self.Replace(type_error, context_string, refers_to_variable, refers_to_expression)
    elif self.refers_to_variable is None and refers_to_variable:
      self.Replace(type_error, context_string, refers_to_variable, refers_to_expression)
    elif 'literal' in self.refers_to_expression:
      self.Replace(type_error, context_string, refers_to_variable, refers_to_expression)

    else:
      pass

  @classmethod
  def BuildNiceMessage(self, context_string, error_message):
    result_lines = [
      color.Format('{underline}Type analysis:{end}'),
      context_string, '',
      color.Format('[ {error}Error{end} ] ') + error_message]
    return '\n'.join(result_lines)
    
  def NiceMessage(self):
    if (isinstance(self.type_error[0], str) and 
        self.type_error[0].startswith('VERBATIM:')):
      return self.type_error[0].removeprefix('VERBATIM:')
    return self.BuildNiceMessage(self.context_string,
                                 self.HelpfulErrorMessage())

  def HelpfulErrorMessage(self):
    result = str(self.type_error)

    if self.refers_to_variable:
      result = color.Format(
        'Variable {warning}%s{end} ' %
        self.refers_to_variable) + result
    else:
      result = color.Format(
        'Expression {warning}{e}{end} ',
        args_dict=dict(e=str(self.refers_to_expression['expression_heritage']))) + result
    return result


def ExpressionFields():
  return ['expression', 'left_hand_side', 'right_hand_side',
          'condition', 'consequence', 'otherwise']

def ExpressionsIterator(node):
  for f in ExpressionFields():
    if f in node:
      yield node[f]
  
  # For inference in structures.
  if 'constraints' in node:
    for x in node['constraints']:
      yield x
  if 'record' in node and 'field_value' not in node['record']:
  # if 'record' in node and 'expression_heritage' in node:
    yield node['record']
  if 'the_list' in node:
    for e in node['the_list']['element']:
      yield e
  if 'inclusion' in node:
    yield node['inclusion']['element']
    yield node['inclusion']['list']


def Walk(node, act):
  """Walking over a dictionary of lists, acting on each element."""
  if isinstance(node, list):
    for v in node:
      Walk(v, act)
  if isinstance(node, dict):
    act(node)
    for k in node:
      if k != 'type':
        Walk(node[k], act)


def ActMindingPodLiterals(node):
  for e in ExpressionsIterator(node):
    if 'literal' in e:
      if 'the_number' in e['literal']:
        reference_algebra.Unify(e['type']['the_type'], reference_algebra.TypeReference('Num'))
      if 'the_string' in e['literal']:
        reference_algebra.Unify(e['type']['the_type'], reference_algebra.TypeReference('Str'))
      if 'the_bool' in e['literal']:
        reference_algebra.Unify(e['type']['the_type'], reference_algebra.TypeReference('Bool'))

def ActClearingTypes(node):
  if 'type' in node:
    del node['type']

def ActRememberingTypes(node):
  if 'type' in node:
    node['remembered_type'] = json.dumps(node['type']['the_type'])

def ActRecallingTypes(node):
  if 'remembered_type' in node:
    remembered_type = reference_algebra.Revive(
      json.loads(node['remembered_type']))
    reference_algebra.Unify(
      node['type']['the_type'],
      remembered_type
    )

class TypesInferenceEngine:
  def __init__(self, parsed_rules, dialect):
    self.parsed_rules = parsed_rules
    self.predicate_argumets_types = {}
    self.dependencies = BuildDependencies(self.parsed_rules)
    self.complexities = BuildComplexities(self.dependencies)
    self.parsed_rules = list(sorted(self.parsed_rules, key=lambda x: self.complexities[x['head']['predicate_name']]))
    self.predicate_signature = types_of_builtins.TypesOfBultins()
    self.typing_preamble = None
    self.collector = None
    self.dialect = dialect

  def CollectTypes(self):
    collector = TypeCollector(self.parsed_rules, self.dialect)
    collector.CollectTypes()
    self.typing_preamble = collector.typing_preamble
    self.collector = collector

  def UpdateTypes(self, rule):
    predicate_name = rule['head']['predicate_name']
    if predicate_name in self.predicate_signature:
       predicate_signature = self.predicate_signature[predicate_name]
    else:
      predicate_signature = {}
      for fv in rule['head']['record']['field_value']:
        field_name = fv['field']
        predicate_signature[field_name] = reference_algebra.TypeReference('Any')
      self.predicate_signature[predicate_name] = predicate_signature

    for fv in rule['head']['record']['field_value']:
      field_name = fv['field']
      v = fv['value']
      if 'expression' in v:
        value = v['expression']
      else:
        value = v['aggregation']['expression']
      value_type = value['type']['the_type']
      if field_name not in predicate_signature:
        raise TypeErrorCaughtException(
          ContextualizedError.BuildNiceMessage(
            rule['full_text'],
            color.Format(
              'Predicate {warning}%s{end} has ' % predicate_name +
              'inconcistent rules, some include field ') +
              color.Format('{warning}%s{end}' % field_name) + ' while others do not.'))
      reference_algebra.Unify(
        predicate_signature[field_name],
        value_type)


  def InferTypes(self):
    for rule in self.parsed_rules:
      if rule['head']['predicate_name'][0] == '@':
        continue
      t = TypeInferenceForRule(rule, self.predicate_signature)
      t.PerformInference()
      self.UpdateTypes(rule)

    for rule in self.parsed_rules:
      Walk(rule, ConcretizeTypes)
    self.CollectTypes()

  def ShowPredicateTypes(self):
    result_lines = []
    for predicate_name, signature in self.predicate_signature.items():
      result_lines.append(RenderPredicateSignature(predicate_name, signature))
    return '\n'.join(result_lines)


def ConcretizeTypes(node):
  if isinstance(node, dict):
    if 'type' in node:
      node['type']['the_type'] = reference_algebra.VeryConcreteType(
        node['type']['the_type'])


def BuildDependencies(rules):
  def ExtractDendencies(rule):
    p = rule['head']['predicate_name']
    dependencies = []
    def ExtractPredicateName(node):
      if 'predicate_name' in node:
        dependencies.append(node['predicate_name'])
    Walk(rule, ExtractPredicateName)
    return p, dependencies
  result = {}
  for rule in rules:
    p, ds = ExtractDendencies(rule)
    result[p] = list(set(sorted(set(ds) - set([p]))) | set(result.get(p, [])))
  return result

def BuildComplexities(dependencies):
  result = {}
  def GetComplexity(p):
    if p not in dependencies:
      return 0
    if p not in result:
      result[p] = 1
      result[p] = 1 + sum(GetComplexity(x) for x in dependencies[p]) 
    return result[p]
  for p in dependencies:
    GetComplexity(p)
  return result


class TypeInferenceForRule:
  def __init__(self, rule, types_of_builtins):
    self.rule = rule
    self.variable_type = {}
    self.type_id_counter = 0
    self.found_error = None
    self.types_of_builtins = types_of_builtins

  def PerformInference(self):
    self.InitTypes()
    self.MindPodLiterals()
    self.MindBuiltinFieldTypes()
    self.IterateInference()

  def GetTypeId(self):
    result = self.type_id_counter
    self.type_id_counter += 1
    return result

  def ActInitializingTypes(self, node):
    for e in ExpressionsIterator(node):
      if 'variable' not in e:  # Variables are convered separately.
        e['type'] = {
          'the_type': reference_algebra.TypeReference('Any'), 
          'type_id': self.GetTypeId()}

  def InitTypes(self):
    WalkInitializingVariables(self.rule, self.GetTypeId)
    Walk(self.rule, self.ActInitializingTypes)

  def MindPodLiterals(self):
    Walk(self.rule, ActMindingPodLiterals)

  def ActMindingBuiltinFieldTypes(self, node):
    def InstillTypes(predicate_name,
                     field_value, signature, output_value):
      copier = reference_algebra.TypeStructureCopier()
      copy = copier.CopyConcreteOrReferenceType
      if output_value:
        output_value_type = output_value['type']['the_type']
        if 'logica_value' in signature:
          reference_algebra.Unify(
            output_value_type,
            copy(signature['logica_value']))
        else:
          error_message = (
            ContextualizedError.BuildNiceMessage(
              output_value['expression_heritage'].Display(),
              'Predicate %s is not a function, but was called as such.' %
                color.Format('{warning}%s{end}') % predicate_name,
            )
          )
          error = reference_algebra.BadType(
            ('VERBATIM:' + error_message,
            output_value_type.target))
          output_value_type.target = reference_algebra.TypeReference.To(error)

      for fv in field_value:
        field_name = fv['field']
        if (field_name not in signature and
            isinstance(field_name, int) and
            'col%d' % field_name in signature):
          field_name = 'col%d' % field_name
        if field_name in signature:
          reference_algebra.Unify(
            fv['value']['expression']['type']['the_type'],
            copy(signature[field_name]))
        elif field_name == '*':
          args = copy(reference_algebra.ClosedRecord(signature))
          reference_algebra.Unify(
            fv['value']['expression']['type']['the_type'],
            reference_algebra.TypeReference.To(args))
        elif '*' in signature:
          args = copy(signature['*'])
          reference_algebra.UnifyRecordField(
            args, field_name,
            fv['value']['expression']['type']['the_type'])
          if isinstance(args.Target(), reference_algebra.BadType):
            error_message = (
              ContextualizedError.BuildNiceMessage(
                fv['value']['expression']['expression_heritage'].Display(),
                'Predicate %s does not have argument %s, but it was addressed.' %
                  (color.Format('{warning}%s{end}') % predicate_name,
                  color.Format('{warning}%s{end}') % fv['field'])
              )
            )
            error = reference_algebra.BadType(
              ('VERBATIM:' + error_message,
              fv['value']['expression']['type']['the_type'].target))
            fv['value']['expression']['type']['the_type'].target = (
              reference_algebra.TypeReference.To(error))        
        else:
          error_message = (
            ContextualizedError.BuildNiceMessage(
              fv['value']['expression']['expression_heritage'].Display(),
              'Predicate %s does not have argument %s, but it was addressed.' %
                (color.Format('{warning}%s{end}') % predicate_name,
                 color.Format('{warning}%s{end}') % fv['field'])
            )
          )
          error = reference_algebra.BadType(
            ('VERBATIM:' + error_message,
            fv['value']['expression']['type']['the_type'].target))
          fv['value']['expression']['type']['the_type'].target = (
            reference_algebra.TypeReference.To(error))

    for e in ExpressionsIterator(node):
      if 'call' in e:
        p = e['call']['predicate_name']
        if p in self.types_of_builtins:
          InstillTypes(p, e['call']['record']['field_value'],
                       self.types_of_builtins[p], e)

    if 'predicate' in node:
      p = node['predicate']['predicate_name']
      if p in self.types_of_builtins:
        InstillTypes(p, node['predicate']['record']['field_value'],
                     self.types_of_builtins[p], None)

    if 'head' in node:
      p = node['head']['predicate_name']
      if p in self.types_of_builtins:
        InstillTypes(p, node['head']['record']['field_value'],
                     self.types_of_builtins[p], None)


  def MindBuiltinFieldTypes(self):
    Walk(self.rule, self.ActMindingBuiltinFieldTypes)

  def ActUnifying(self, node):
    if 'unification' in node:
      left_type = node['unification']['left_hand_side']['type']['the_type']
      right_type = node['unification']['right_hand_side']['type']['the_type']
      reference_algebra.Unify(left_type, right_type)

  def ActUnderstandingSubscription(self, node):
    if 'subscript' in node and 'record' in node['subscript']:
      record_type = node['subscript']['record']['type']['the_type']
      field_type = node['type']['the_type']
      field_name = node['subscript']['subscript']['literal']['the_symbol']['symbol']
      reference_algebra.UnifyRecordField(
        record_type, field_name, field_type)

  def ActMindingRecordLiterals(self, node):
    if 'type' in node and 'record' in node:
      record_type = node['type']['the_type']
      reference_algebra.Unify(
        record_type,
        reference_algebra.TypeReference(
        reference_algebra.OpenRecord()))
      for fv in node['record']['field_value']:
        field_type = fv['value']['expression']['type']['the_type']
        field_name = fv['field']
        reference_algebra.UnifyRecordField(
          record_type, field_name, field_type)
        # print('>>>', node)

      node['type']['the_type'].CloseRecord()

  def ActMindingTypingPredicateLiterals(self, node):
    if 'type' in node and 'literal' in node and 'the_predicate' in node['literal']:
      predicate_name = node['literal']['the_predicate']['predicate_name']
      if predicate_name in ['Str', 'Num', 'Bool', 'Time']:
        reference_algebra.Unify(node['type']['the_type'],
                                reference_algebra.TypeReference(predicate_name))

  def ActMindingListLiterals(self, node):
    if 'type' in node and 'literal' in node and 'the_list' in node['literal']:
      list_type = node['type']['the_type']
      for e in node['literal']['the_list']['element']:
        reference_algebra.UnifyListElement(
          list_type, e['type']['the_type'])
      else:
        reference_algebra.UnifyListElement(
          list_type, reference_algebra.TypeReference('Any'))

  def ActMindingInclusion(self, node):
    if 'inclusion' in node:
      list_type = node['inclusion']['list']['type']['the_type']
      element_type = node['inclusion']['element']['type']['the_type']
      reference_algebra.UnifyListElement(
        list_type, element_type
      )

  def ActMindingCombine(self, node):
    if 'combine' in node:
      field_value = node['combine']['head']['record']['field_value']
      [logica_value] = [fv['value']
                        for fv in field_value
                        if fv['field'] == 'logica_value']
      reference_algebra.Unify(
        node['type']['the_type'],
        logica_value['aggregation']['expression']['type']['the_type']
      )

  def ActMindingImplications(self, node):
    if 'implication' in node:
      for if_then in node['implication']['if_then']:
        reference_algebra.Unify(
          node['type']['the_type'],
          if_then['consequence']['type']['the_type']
        )
      reference_algebra.Unify(
        node['type']['the_type'],
        node['implication']['otherwise']['type']['the_type']
      )

  def IterateInference(self):
    Walk(self.rule, self.ActMindingTypingPredicateLiterals)
    Walk(self.rule, self.ActMindingRecordLiterals)
    Walk(self.rule, self.ActUnifying)
    Walk(self.rule, self.ActUnderstandingSubscription)
    Walk(self.rule, self.ActMindingListLiterals)
    Walk(self.rule, self.ActMindingInclusion)
    Walk(self.rule, self.ActMindingCombine)
    Walk(self.rule, self.ActMindingImplications)

def RenderPredicateSignature(predicate_name, signature):
  def FieldValue(f, v):
    if isinstance(f, int):
      field = ''
    else:
      field = f + ': '
    value = reference_algebra.RenderType(reference_algebra.VeryConcreteType(v))
    return field + value
  field_values = [FieldValue(f, v) for f, v in signature.items()
                  if f != 'logica_value']
  signature_str = ', '.join(field_values)
  maybe_value = [
    ' = ' + reference_algebra.RenderType(
      reference_algebra.VeryConcreteType(v))
    for f, v in signature.items() if f == 'logica_value']
  value_or_nothing = maybe_value[0] if maybe_value else ''
  result = f'type {predicate_name}({signature_str}){value_or_nothing};'
  return result


class TypeInferenceForStructure:
  def __init__(self, structure, signatures, dialect):
    self.structure = structure
    self.signatures = signatures
    self.collector = None
    self.quazy_rule = None
    self.dialect = dialect

  def PerformInference(self):
    quazy_rule = self.BuildQuazyRule()
    self.quazy_rule = quazy_rule
    Walk(quazy_rule, ActRememberingTypes)
    Walk(quazy_rule, ActClearingTypes)
    inferencer = TypeInferenceForRule(quazy_rule, self.signatures)
    inferencer.PerformInference()
    Walk(quazy_rule, ActRecallingTypes)

    Walk(quazy_rule, ConcretizeTypes)
    collector = TypeCollector([quazy_rule], self.dialect)
    collector.CollectTypes()
    self.collector = collector

    import json
    # 
    # print('>> quazy rule:', json.dumps(quazy_rule, indent=' '))

  def BuildQuazyRule(self):
    result = {}
    result['quazy_body'] = self.BuildQuazyBody()
    result['select'] = self.BuildSelect()
    result['unnestings'] = self.BuildUnnestings()
    result['constraints'] = self.structure.constraints
    return result
  
  def BuildUnnestings(self):
    # print('>> unnestings', self.structure.unnestings)
    result = []
    for variable, the_list in self.structure.unnestings:
      result.append(
        {'inclusion': {
          'element': variable,
          'list': the_list
        }}
      )
    return result

  def BuildQuazyBody(self):
    # print('>> tables, vars_map: ', self.structure.tables, self.structure.vars_map)
    calls = {}

    for table_id, predicate in self.structure.tables.items():
      calls[table_id] = {
        'predicate': {'predicate_name': predicate,
                      'record': {'field_value': []}}}
    
    for (table_id, field), variable in self.structure.vars_map.items():
      if table_id is None:
        # This is from unnestings. I don't recall why are those even here :-(
        # Need to clarify.
        continue
      calls[table_id]['predicate']['record']['field_value'].append(
        {'field': field,
         'value': {'expression': {'variable': {'var_name': variable}}}
        }
      )

    return list(calls.values())

  def BuildSelect(self):
    field_values = []
    result = {'record': {'field_value': field_values}}
    for k, v in  self.structure.select.items():
      field_values.append({
        'field': k,
        'value': {'expression': v}
      })
    return result

class TypeErrorCaughtException(Exception):
  """Exception thrown when user-error is detected at rule-compile time."""

  def __init__(self, message):
    super(TypeErrorCaughtException, self).__init__(message)

  def ShowMessage(self, stream=sys.stderr):
    print(str(self), file=stream)


class TypeErrorChecker:
  def __init__(self, typed_rules):
    self.typed_rules = typed_rules

  def CheckForError(self, mode='print'):    
    self.found_error = self.SearchTypeErrors()
    if self.found_error.type_error:
      if mode == 'print':
        print(self.found_error.NiceMessage())
      elif mode == 'raise':
        raise TypeErrorCaughtException(self.found_error.NiceMessage())
      else:
        assert False
      
  def SearchTypeErrors(self):
    found_error = ContextualizedError()
    def LookForError(node):
      nonlocal found_error
      if 'type' in node:
        t = reference_algebra.VeryConcreteType(node['type']['the_type'])
        if isinstance(t, reference_algebra.BadType):
          if 'variable' in node:
            v = node['variable']['var_name']
          else:
            v = None
          # Combines don't have expression_heritage.
          # assert 'expression_heritage' in node, (node, t)
          if 'expression_heritage' not in node:
            found_error.ReplaceIfMoreUseful(
              t, 'UNKNOWN LOCATION', v,
              node)
          else:
            found_error.ReplaceIfMoreUseful(
              t, node['expression_heritage'].Display(), v,
              node)
    for rule in self.typed_rules:
      Walk(rule, LookForError)
      if found_error.type_error:
        return found_error
    return found_error


def WalkInitializingVariables(node, get_type):
  """Initialize variables minding combines contexts."""
  type_of_variable = {}
  def Jog(node, found_combines):
    nonlocal type_of_variable
    if isinstance(node, list):
      for v in node:
        Jog(v, found_combines)
    if isinstance(node, dict):
      if 'variable' in node:
        var_name = node['variable']['var_name']
        if var_name not in type_of_variable:
          type_of_variable[var_name] = {
            'the_type': reference_algebra.TypeReference('Any'),
            'type_id': get_type()}
        node['type'] = type_of_variable[var_name]
      for k in node:
        if k != 'type':
          if k != 'combine':
            Jog(node[k], found_combines)
          else:
            found_combines.append(node[k])
  def JogPredicate(node):
    nonlocal type_of_variable
    found_combines = []
    Jog(node, found_combines)
    backed_up_types = {k: v for k, v in type_of_variable.items()}
    for n in found_combines:
      JogPredicate(n)
      type_of_variable = backed_up_types
  JogPredicate(node)

def Fingerprint(s):
  return int(hashlib.md5(str(s).encode()).hexdigest()[:16], 16)

def RecordTypeName(type_render):
  return 'logicarecord%d' % (Fingerprint(type_render) % 1000000000)

class TypeCollector:
  def __init__(self, parsed_rules, dialect):
    self.parsed_rules = parsed_rules
    self.type_map = {}
    self.psql_struct_type_name = {}
    self.psql_type_definition = {}
    self.definitions = []
    self.typing_preamble = ''
    self.psql_type_cache = {}
    self.dialect = dialect

  def ActPopulatingTypeMap(self, node):
    if 'type' in node:
      t = node['type']['the_type']
      t_rendering = reference_algebra.RenderType(t)
      self.type_map[t_rendering] = t
      node['type']['rendered_type'] = t_rendering
      if 'combine' in node and reference_algebra.IsFullyDefined(t):
        node['type']['combine_psql_type'] = self.PsqlType(t)
      if reference_algebra.IsFullyDefined(t):
        self.psql_type_cache[t_rendering] = self.PsqlType(t)
      if isinstance(t, dict) and reference_algebra.IsFullyDefined(t):
        node['type']['type_name'] = RecordTypeName(t_rendering)
      if isinstance(t, list) and reference_algebra.IsFullyDefined(t):
        [e] = t
        node['type']['element_type_name'] = self.PsqlType(e)

  def CollectTypes(self):
    Walk(self.parsed_rules, self.ActPopulatingTypeMap)
    for t in self.type_map:
      the_type = self.type_map[t]
      if isinstance(the_type, dict):
        if not reference_algebra.IsFullyDefined(the_type):
          continue
        self.psql_struct_type_name[t] = RecordTypeName(t)
    self.BuildPsqlDefinitions()

  def PsqlType(self, t):
    if t == 'Str':
      return 'text'
    if t == 'Num':
      return 'numeric'
    if t == 'Bool':
      return 'bool'
    if t == 'Time':
      return 'timestamp'
    if isinstance(t, dict):
      return RecordTypeName(reference_algebra.RenderType(t))
    if isinstance(t, list):
      [e] = t
      return self.PsqlType(e) + '[]'
    assert False, t

  def BuildPsqlDefinitions(self):
    for t in self.psql_struct_type_name:
      arg_name = lambda x: (
        '"cast"' if x == 'cast'  # Escaping keyword.
        else (x if isinstance(x, str) else 'col%d' % x))
      args = ', '.join(
        arg_name(f) + ' ' + self.PsqlType(v)
        for f, v in sorted(self.type_map[t].items(),
                           key=reference_algebra.StrIntKey)
      )
      dialect_interjection = ''
      if self.dialect == 'duckdb':
        dialect_interjection = 'struct'
      self.psql_type_definition[t] = f'create type %s as %s(%s);' % (
        self.psql_struct_type_name[t],
        dialect_interjection,
        args)

    if self.dialect in ['psql', 'sqlite', 'bigquery']:
      wrap = lambda n, d: (
        f"-- Logica type: {n}\n" +
        f"if not exists (select 'I(am) :- I(think)' from pg_type where typname = '{n}') then {d} end if;"
      )
    elif self.dialect == 'duckdb':
      wrap = lambda n, d: (
        f"-- Logica type: {n}\n" +
        f"drop type if exists {n} cascade; {d}\n"
      )
    else:
      assert False, 'Unknown psql dialect: ' + self.dialect
    
    self.definitions = {
      t: wrap(self.psql_struct_type_name[t], self.psql_type_definition[t])
      for t in sorted(self.psql_struct_type_name, key=len)
      if self.psql_struct_type_name[t] not in ['logicarecord893574736']}
    self.typing_preamble = BuildPreamble(self.definitions, self.dialect)

def BuildPreamble(definitions, dialect):
  if dialect in ['psql', 'sqlite', 'bigquery']:
    return 'DO $$\nBEGIN\n' + '\n'.join(definitions.values()) + '\nEND $$;\n'
  elif dialect == 'duckdb':
    return '\n'.join(definitions.values())
  else:
    assert False, 'Unknown psql dialect: ' + dialect

def ArgumentNames(signature):
  result = []
  for v in signature:
    if isinstance(v, int):
      result.append('col%d' % v)
    else:
      result.append(v)
  return result