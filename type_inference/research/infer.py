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

    if (isinstance(self.type_error[0], dict) and
        isinstance(self.type_error[1], dict)):
      if isinstance(self.type_error[0],
                    reference_algebra.ClosedRecord):
        a, b = self.type_error
      else:
        b, a = self.type_error
      if (isinstance(a, reference_algebra.ClosedRecord) and
          isinstance(b, reference_algebra.OpenRecord) and
          list(b)[0] not in a.keys() ):
        result = (
          'record ' + str(a) + ' does not have field ' + list(b)[0] + '.'
        )

    if self.refers_to_variable:
      result = color.Format(
        'Variable {warning}%s{end} ' %
        self.refers_to_variable) + result
    else:
      result = color.Format(
        'Expression {warning}%s{end} ' %
        str(self.refers_to_expression['expression_heritage']) + result
      )
    return result


def ExpressionFields():
  return ['expression', 'left_hand_side', 'right_hand_side']

def ExpressionsIterator(node):
  for f in ExpressionFields():
    if f in node:
      yield node[f]
  if 'record' in node and 'field_value' not in node['record']:
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


class TypesInferenceEngine:
  def __init__(self, parsed_rules):
    self.parsed_rules = parsed_rules
    self.predicate_argumets_types = {}
  
  def InferTypes(self):
    for rule in self.parsed_rules:
      t = TypeInferenceForRule(rule)
      t.PerformInference()
    
    def Concretize(node):
      if isinstance(node, dict):
        if 'type' in node:
          node['type']['the_type'] = reference_algebra.VeryConcreteType(
            node['type']['the_type'])
    for rule in self.parsed_rules:
      Walk(rule, Concretize)


class TypeInferenceForRule:
  def __init__(self, rule):
    self.rule = rule
    self.variable_type = {}
    self.type_id_counter = 0
    self.types_of_builtins = types_of_builtins.TypesOfBultins()
    self.found_error = None

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
      i = self.GetTypeId()
      if 'variable' in e:
        var_name = e['variable']['var_name']
        use_type = self.variable_type.get(
          var_name,
          {'the_type': reference_algebra.TypeReference('Any'), 'type_id': i})
        self.variable_type[var_name] = use_type
      else:
        use_type = {'the_type': reference_algebra.TypeReference('Any'), 'type_id': i}
      e['type'] = use_type

  def InitTypes(self):
    Walk(self.rule, self.ActInitializingTypes)

  def MindPodLiterals(self):
    Walk(self.rule, ActMindingPodLiterals)

  def ActMindingBuiltinFieldTypes(self, node):
    for e in ExpressionsIterator(node):
      if 'call' in e:
        p = e['call']['predicate_name']
        if p in self.types_of_builtins:
          copier = reference_algebra.TypeStructureCopier()
          copy = copier.CopyConcreteOrReferenceType

          reference_algebra.Unify(
            e['type']['the_type'],
            copy(self.types_of_builtins[p]['logica_value']))
          for fv in e['call']['record']['field_value']:
            if fv['field'] in self.types_of_builtins[p]:
              reference_algebra.Unify(
                fv['value']['expression']['type']['the_type'],
                copy(self.types_of_builtins[p][fv['field']]))
    if 'predicate' in node:
      p = node['predicate']['predicate_name']
      if p in self.types_of_builtins:
        copier = reference_algebra.TypeStructureCopier()
        copy = copier.CopyConcreteOrReferenceType
        for fv in node['predicate']['record']['field_value']:
          if fv['field'] in self.types_of_builtins[p]:
            reference_algebra.Unify(
              fv['value']['expression']['type']['the_type'],
              copy(self.types_of_builtins[p][fv['field']]))

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
      for fv in node['record']['field_value']:
        record_type = node['type']['the_type']
        field_type = fv['value']['expression']['type']['the_type']
        field_name = fv['field']
        reference_algebra.UnifyRecordField(
          record_type, field_name, field_type)
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

  def IterateInference(self):
    Walk(self.rule, self.ActMindingRecordLiterals)
    Walk(self.rule, self.ActUnifying)
    Walk(self.rule, self.ActUnderstandingSubscription)
    Walk(self.rule, self.ActMindingListLiterals)
    Walk(self.rule, self.ActMindingInclusion)
    
    self.found_error = self.SearchTypeErrors()
    if self.found_error.type_error:
      print(self.found_error.NiceMessage())

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
          found_error.ReplaceIfMoreUseful(
            t, node['expression_heritage'].Display(), v,
            node)
    Walk(self.rule, LookForError)
    return found_error
