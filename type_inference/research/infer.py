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
else:
  from ..type_inference.research import algebra

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


def ActInitializingTypes(node):
  for f in ExpressionFields():
    if f in node:
      node[f]['type'] = 'Any'


def ActMindingPodLiterals(node):
  for f in ExpressionFields():
    if f in node:
      if 'literal' in node['f']:
        if 'the_number' in node['f']['literal']:
          node[f]['type'] = algebra.Intersect(node[f]['type'], 'Num')
        if 'the_string' in node['f']['literal']:
          node[f]['type'] = algebra.Intersect(node[f]['type'], 'Str')

class TypesInferenceEngine:
  def __init__(self, parsed_rules):
    self.parsed_rules = parsed_rules
    self.predicate_argumets_types = {}

  def InitTypes(self):
    for rule in self.parsed_rules:
      Walk(rule, ActInitializingTypes)

  def MindPodLiterals(self):
    for rule in self.parsed_rules:
      Walk(rule, ActMindingPodLiterals)

  def InferTypes(self):
    self.InitTypes()
    
