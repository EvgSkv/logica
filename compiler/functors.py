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

"""Functors library.

This is for running @Make instructions.

In the context of @Make we are thinking of each predicate as also a function
from the set of predicates to itself. The predicates that it uses in the
definition are arguments of this function.

Such functions that map predicates to predicates we call 'functors'.

At the moment any functor is a predicate, but in the future we may want to
introduce more abstact functors. E.g.: Apply(F, G) := F(G);
This could potentially be useful for limited recursion.
"""

import collections
import copy
import sys

from common import color
from parser_py import parse


class FunctorError(Exception):
  """Exception thrown when Make is bad."""

  def __init__(self, message, functor_name):
    super(FunctorError, self).__init__(message)
    self.functor_name = functor_name

  def ShowMessage(self):
    print(color.Format('{underline}Making{end}:'), file=sys.stderr)
    print(self.functor_name, file=sys.stderr)
    print(color.Format('\n[ {error}Error{end} ] ') + self.message,
          file=sys.stderr)


def Walk(x, act, should_enter):
  """Walking over a dictionary of lists, modifying and/or collecting info."""
  r = []
  r.extend(act(x))
  if isinstance(x, list):
    for v in x:
      r.extend(Walk(v, act, should_enter))
  if isinstance(x, dict):
    for k in x:
      if should_enter(k):
        r.extend(Walk(x[k], act, should_enter))
  return set(r)


class Functors(object):
  """A class for creating new functors."""

  def __init__(self, rules):
    self.rules = rules
    self.extended_rules = copy.deepcopy(rules)
    self.rules_of = parse.DefinedPredicatesRules(rules)
    self.predicates = set(self.rules_of)
    self.direct_args_of = self.BuildDirectArgsOf()
    self.args_of = {}
    self.creation_count = 0
    self.cached_calls = {}
    for p in self.predicates:
      self.ArgsOf(p)

  def UpdateStructure(self):
    """Updates rules_of and args_of maps after extebded_rules update."""
    self.rules_of = parse.DefinedPredicatesRules(self.extended_rules)
    self.predicates = set(self.rules_of)
    self.direct_args_of = self.BuildDirectArgsOf()
    # Resetting args_of, to process the new predicates that were added.
    self.args_of = {}
    for p in self.predicates:
      self.ArgsOf(p)

  def ParseMakeInstruction(self, predicate, instruction):
    """Parses Make instruction from syntax tree."""
    error_message = 'Bad Make instruction: %s' % instruction
    if '1' not in instruction or '2' not in instruction:
      raise FunctorError(error_message, predicate)
    if 'predicate_name' not in instruction['1']:
      raise FunctorError(error_message, predicate)
    applicant = instruction['1']['predicate_name']
    args_map = {}
    for arg_name, arg_value_dict in instruction['2'].items():
      if 'predicate_name' not in arg_value_dict:
        raise FunctorError(error_message, predicate)
      args_map[arg_name] = arg_value_dict['predicate_name']
    return predicate, applicant, args_map

  def Describe(self):
    return 'DirectArgs: %s,\nArgs: %s' % (self.direct_args_of, self.args_of)

  def BuildDirectArgsOf(self):
    """Builds a map of direct arguments of a functor."""
    def ExtractPredicateName(x):
      if isinstance(x, dict) and 'predicate_name' in x:
        return [x['predicate_name']]
      return []
    direct_args_of = {}
    for functor, rules in self.rules_of.items():
      args = set()
      for rule in rules:
        args |= Walk(rule, ExtractPredicateName, lambda _: True)
      args -= set([functor])
      direct_args_of[functor] = args
    return direct_args_of

  def ArgsOf(self, functor):
    """Arguments of functor. Retrieving from cache, or computing."""
    if functor not in self.args_of:
      self.args_of[functor] = self.BuildArgs(functor)
    return self.args_of[functor]

  def BuildArgs(self, functor):
    """Returning all arguments of a functor."""
    result = set()
    if functor not in self.direct_args_of:
      # Assuming this is built-in or table.
      return result
    queue = collections.deque(self.direct_args_of[functor])
    while queue:
      e = queue.popleft()
      result.add(e)
      for a in self.ArgsOf(e):
        if a not in result:
          queue.append(a)
    return result

  def AllRulesOf(self, functor):
    """Returning all rules relevant to a predicate."""
    result = []
    if functor not in self.rules_of:
      return result
    result.extend(self.rules_of[functor])
    for f in self.args_of[functor]:
      if f in self.rules_of:
        result.extend(self.rules_of[f])
    return copy.deepcopy(result)

  def Make(self, predicate, instruction):
    """Make a new predicate according to instruction."""
    self.CallFunctor(*self.ParseMakeInstruction(predicate, instruction))

  def MakeAll(self, predicate_to_instruction):
    """Making all required predicates."""
    # We needs to build them in the order of dependency.
    needs_building = set(
        self.ParseMakeInstruction(p, i)[0] for p, i in predicate_to_instruction)
    while needs_building:
      something_built = False
      for (new_predicate, instruction) in sorted(predicate_to_instruction):
        name, applicant, args_map = self.ParseMakeInstruction(new_predicate,
                                                              instruction)
        if (new_predicate not in needs_building or
            applicant in needs_building or
            (set(args_map.values()) & needs_building)):
          continue
        self.Make(new_predicate, instruction)
        something_built = True
        needs_building.remove(name)
      if needs_building and not something_built:
        raise FunctorError('Could not resolve Make order.',
                           str(needs_building))
    if False:
      with open('/tmp/functors.dot', 'w') as w:
        w.write('digraph Functors {\n')
        for f, args in self.direct_args_of.items():
          # For cleaner graph:
          if f.startswith('@') or f == '++?':
            continue
          for arg in args:
            if arg in ['||', '&&', '==', '<=', '>=', '<', '>', '!=', '++?',
                       '++', '+', '-', '*', '/', '%', '^', ' In ', '!',
                       'Agg+', 'Greatest']:
              continue  # For cleaner graph.
            w.write('"%s" -> "%s";\n' % (f, arg))
        w.write('}\n')

  def CollectAnnotations(self, predicates):
    """Collecting annotations of predictes."""
    predicates = set(predicates)
    result = []
    for annotation, rules in self.rules_of.items():
      if annotation not in ['@Limit', '@OrderBy', '@Ground',
                            '@NoInject']:
        continue
      for rule in rules:
        if rule['head']['record']['field_value'][0]['value']['expression'][
            'literal']['the_predicate']['predicate_name'] in predicates:
          result.append(rule)
    return copy.deepcopy(result)

  def CallKey(self, functor, args_map):
    """A string representing a call of a functor with arguments."""
    relevant_args = {k: v
                     for k, v in args_map.items()
                     if k in self.ArgsOf(functor)}
    args = ','.join('%s: %s' % (k, v) for k, v in sorted(relevant_args.items()))
    result = '%s(%s)' % (functor, args)
    return result

  def CallFunctor(self, name, applicant, args_map):
    """Calling a functor applicant(args_map), storing result to 'name'."""
    bad_args = set(args_map.keys()) - set(self.args_of[applicant])
    if bad_args:
      raise FunctorError(
          'Functor %s is applied to arguments %s, which it does not '
          'have.' % (applicant, color.Warn(','.join(bad_args))),
          name)
    self.creation_count += 1
    rules = self.AllRulesOf(applicant)
    args = set(args_map)
    rules = [r for r in rules
             if ((args & self.args_of[r['head']['predicate_name']]) or
                 r['head']['predicate_name'] == applicant)]
    if not rules:
      raise FunctorError(
          'Rules for %s when making %s are not found' % (applicant, name),
          name)
    # This eventually maps all args to substiturions, as well as all predictes
    # which use one of the args into a newly created predicate names.
    extended_args_map = copy.deepcopy(args_map)
    rules_to_update = []
    cache_update = {}
    predicates_to_annotate = set()
    for r in sorted(rules, key=str):
      rule_predicate_name = r['head']['predicate_name']
      if rule_predicate_name == applicant:
        extended_args_map[rule_predicate_name] = name
        rules_to_update.append(r)
        predicates_to_annotate.add(rule_predicate_name)
      else:
        call_key = self.CallKey(rule_predicate_name, args_map)
        if call_key in self.cached_calls:
          new_predicate_name = self.cached_calls[call_key]
          extended_args_map[rule_predicate_name] = new_predicate_name
        else:
          new_predicate_name = (
              rule_predicate_name + '_f%d' % self.creation_count)
          extended_args_map[rule_predicate_name] = new_predicate_name
          cache_update[call_key] = new_predicate_name
          rules_to_update.append(r)
          predicates_to_annotate.add(rule_predicate_name)

    rules = rules_to_update
    self.cached_calls.update(cache_update)
    # Collect annotations of all involved predicates.
    # Newly created predicates inherit annotations of predicates from which
    # they were created.
    # Arguments values of the functor do not inherit annotations of the
    # arguments, as that would collide with their performance in other
    # contexts.
    # In particular it means that functors should not use @Limit and @OrderBy
    # of the arguments to express the logic. Instead they should create simple
    # predicates reading from the agument and annotate those.
    annotations = self.CollectAnnotations(list(predicates_to_annotate))
    rules.extend(annotations)
    def ReplacePredicate(x):
      if isinstance(x, dict) and 'predicate_name' in x:
        if x['predicate_name'] in extended_args_map:
          x['predicate_name'] = extended_args_map[x['predicate_name']]
      return []
    Walk(rules, ReplacePredicate, lambda _: True)
    self.extended_rules.extend(rules)
    self.UpdateStructure()
