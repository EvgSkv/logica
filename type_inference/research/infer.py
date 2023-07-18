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

  def NiceMessage(self):
    result_lines = [
      color.Format('{underline}Type analysis:{end}'),
      self.context_string, '',
      color.Format('[ {error}Error{end} ] ') + self.HelpfulErrorMessage()]
    
    return '\n'.join(result_lines)

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
  def __init__(self, parsed_rules):
    self.parsed_rules = parsed_rules
    self.predicate_argumets_types = {}
    self.dependencies = BuildDependencies(self.parsed_rules)
    self.complexities = BuildComplexities(self.dependencies)
    self.parsed_rules = list(sorted(self.parsed_rules, key=lambda x: self.complexities[x['head']['predicate_name']]))
    self.types_of_builtins = types_of_builtins.TypesOfBultins()
    self.typing_preamble = None

  def CollectTypes(self):
    collector = TypeCollector(self.parsed_rules)
    collector.CollectTypes()
    self.typing_preamble = collector.typing_preamble

  def UpdateTypes(self, rule):
    predicate_name = rule['head']['predicate_name']
    if predicate_name in self.types_of_builtins:
       predicate_signature = self.types_of_builtins[predicate_name]
    else:
      predicate_signature = {}
      for fv in rule['head']['record']['field_value']:
        field_name = fv['field']
        predicate_signature[field_name] = reference_algebra.TypeReference('Any')
      self.types_of_builtins[predicate_name] = predicate_signature

    for fv in rule['head']['record']['field_value']:
      field_name = fv['field']
      v = fv['value']
      if 'expression' in v:
        value = v['expression']
      else:
        value = v['aggregation']['expression']
      value_type = value['type']['the_type']
      reference_algebra.Unify(
        predicate_signature[field_name],
        value_type)


  def InferTypes(self):
    for rule in self.parsed_rules:
      if rule['head']['predicate_name'][0] == '@':
        continue
      t = TypeInferenceForRule(rule, self.types_of_builtins)
      t.PerformInference()
      self.UpdateTypes(rule)

    for rule in self.parsed_rules:
      Walk(rule, ConcretizeTypes)
    self.CollectTypes()

  def ShowPredicateTypes(self):
    result_lines = []
    for predicate_name, signature in self.types_of_builtins.items():
      result_lines.append(RenderPredicateSignature(predicate_name, signature))
    return '\n'.join(result_lines)


def ConcretizeTypes(node):
  # print('>> concretizing', node)
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
    result[p] = list(sorted(set(ds) - set([p])))
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
    def InstillTypes(field_value, signature, output_value_type):
      copier = reference_algebra.TypeStructureCopier()
      copy = copier.CopyConcreteOrReferenceType
      if output_value_type:
        reference_algebra.Unify(
          output_value_type,
          copy(signature['logica_value']))
      for fv in field_value:
        if fv['field'] in signature:
          reference_algebra.Unify(
            fv['value']['expression']['type']['the_type'],
            copy(signature[fv['field']]))

    for e in ExpressionsIterator(node):
      if 'call' in e:
        p = e['call']['predicate_name']
        if p in self.types_of_builtins:
          InstillTypes(e['call']['record']['field_value'],
                       self.types_of_builtins[p],
                       e['type']['the_type'])

    if 'predicate' in node:
      p = node['predicate']['predicate_name']
      if p in self.types_of_builtins:
        InstillTypes(node['predicate']['record']['field_value'],
                     self.types_of_builtins[p], None)

    if 'head' in node:
      p = node['head']['predicate_name']
      if p in self.types_of_builtins:
        InstillTypes(node['head']['record']['field_value'],
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

  def ActMindingListLiterals(self, node):
    if 'type' in node and 'literal' in node and 'the_list' in node['literal']:
      list_type = node['type']['the_type']
      for e in node['literal']['the_list']['element']:
        reference_algebra.UnifyListElement(
          list_type, e['type']['the_type'])

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
  def __init__(self, structure, signatures):
    self.structure = structure
    self.signatures = signatures

  def PerformInference(self):
    quazy_rule = self.BuildQuazyRule()
    Walk(quazy_rule, ActRememberingTypes)
    Walk(quazy_rule, ActClearingTypes)
    inferencer = TypeInferenceForRule(quazy_rule, self.signatures)
    inferencer.PerformInference()
    Walk(quazy_rule, ActRecallingTypes)
          
    Walk(quazy_rule, ConcretizeTypes)
    collector = TypeCollector([quazy_rule])
    collector.CollectTypes()

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
  def __init__(self, parsed_rules):
    self.parsed_rules = parsed_rules
    self.type_map = {}
    self.psql_struct_type_name = {}
    self.psql_type_definition = {}
    self.definitions = []
    self.typing_preamble = ''
  
  def ActPopulatingTypeMap(self, node):
    if 'type' in node:
      t = node['type']['the_type']
      t_rendering = reference_algebra.RenderType(t)
      self.type_map[t_rendering] = t
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
    if isinstance(t, dict):
      return RecordTypeName(reference_algebra.RenderType(t))
    if isinstance(t, list):
      [e] = t
      return self.PsqlType(e) + '[]'
    assert False, t

  def BuildPsqlDefinitions(self):
    for t in self.psql_struct_type_name:
      args = ', '.join(
        f + ' ' + self.PsqlType(v)
        for f, v in sorted(self.type_map[t].items())
      )
      self.psql_type_definition[t] = f'create type %s as (%s);' % (
        self.psql_struct_type_name[t], args)

    wrap = lambda n, d: (
      f"if not exists (select 'I(am) :- I(think)' from pg_type where typname = '{n}') then {d} end if;"
    )
    self.definitions = [
      wrap(self.psql_struct_type_name[t], self.psql_type_definition[t])
      for t in sorted(self.psql_struct_type_name, key=len)]

    self.typing_preamble = 'DO $$\nBEGIN\n' + '\n'.join(self.definitions) + '\nEND $$;\n'