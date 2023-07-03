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
  from type_inference.research import algebra
  from type_inference.research import types_of_builtins
else:
  from ..research import algebra
  from ..research import types_of_builtins


def ExpressionFields():
  return ['expression', 'left_hand_side', 'right_hand_side']


def Walk(node, act):
  """Walking over a dictionary of lists, acting on each element."""
  if isinstance(node, list):
    for v in node:
      Walk(v, act)
  if isinstance(node, dict):
    act(node)
    for k in node:
      Walk(node[k], act)


def ActMindingPodLiterals(node):
  for f in ExpressionFields():
    if f in node:
      if 'literal' in node[f]:
        if 'the_number' in node[f]['literal']:
          node[f]['type']['the_type'] = algebra.Intersect(node[f]['type']['the_type'], 'Num')
        if 'the_string' in node[f]['literal']:
          node[f]['type']['the_type'] = algebra.Intersect(node[f]['type']['the_type'], 'Str')


class TypesInferenceEngine:
  def __init__(self, parsed_rules):
    self.parsed_rules = parsed_rules
    self.predicate_argumets_types = {}
    self.variable_type = {}
    self.type_id_counter = 0
    self.types_of_builtins = types_of_builtins.TypesOfBultins()
  
  def GetTypeId(self):
    result = self.type_id_counter
    self.type_id_counter += 1
    return result

  def ActInitializingTypes(self, node):
    for f in ExpressionFields():
      if f in node:
        i = self.GetTypeId()
        if 'variable' in node[f]:
          var_name = node[f]['variable']['var_name']
          use_type = self.variable_type.get(
            var_name,
            {'the_type': 'Any', 'type_id': i})
          self.variable_type[var_name] = use_type
        else:
          use_type = {'the_type': 'Any', 'type_id': i}
        node[f]['type'] = use_type

  def InitTypes(self):
    for rule in self.parsed_rules:
      Walk(rule, self.ActInitializingTypes)

  def MindPodLiterals(self):
    for rule in self.parsed_rules:
      Walk(rule, ActMindingPodLiterals)

  def ActMindingBuiltinFieldTypes(self, node):
    for f in ExpressionFields():
      if f in node:
        e = node[f]
        if 'call' in e:
          p = e['call']['predicate_name']
          t = e['type']['the_type']
          if p in self.types_of_builtins:
            e['type']['the_type'] = algebra.Intersect(t, self.types_of_builtins[p])

  def MindBuiltinFieldTypes(self):
    for rule in self.parsed_rules:
      Walk(rule, self.ActMindingBuiltinFieldTypes)

  def InferTypes(self):
    self.InitTypes()
    self.MindPodLiterals()
    self.MindBuiltinFieldTypes()
    for rule in self.parsed_rules:
      TypeInferenceForRule(rule)


class TypeInferenceForRule:
  def __init__(self, rule):
    self.rule = rule
    self.inference_complete = False
    self.IterateInference()

  def ActUnifying(self, node):
    if 'unification' in node:
      left_type = node['unification']['left_hand_side']['type']['the_type']
      right_type = node['unification']['right_hand_side']['type']['the_type']
      new_type = algebra.Intersect(left_type, right_type)
      if new_type != left_type:
        self.inference_complete = False
        node['unification']['left_hand_side']['type']['the_type'] = new_type
      if new_type != right_type:
        self.inference_complete = False
        node['unification']['right_hand_side']['type']['the_type'] = new_type
      
  def IterateInference(self):
    while not self.inference_complete:
      self.inference_complete = True
      Walk(self.rule, self.ActUnifying)
