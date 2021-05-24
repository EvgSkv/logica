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

if '.' not in __package__:
  from common import color
  from compiler.dialect_libraries import recursion_library
  from parser_py import parse
else:
  from ..common import color
  from ..compiler.dialect_libraries import recursion_library
  from ..parser_py import parse


class FunctorError(Exception):
  """Exception thrown when Make is bad."""

  def __init__(self, message, functor_name):
    super(FunctorError, self).__init__(message)
    self.functor_name = functor_name
    self.message = message

  def ShowMessage(self):
    print(color.Format('{underline}Making{end}:'), file=sys.stderr)
    print(self.functor_name, file=sys.stderr)
    print(color.Format('\n[ {error}Error{end} ] ') + self.message,
          file=sys.stderr)

def Walk(x, act):
  """Walking over a dictionary of lists, modifying and/or collecting info."""
  r = set()
  r |= set(act(x))
  if isinstance(x, list):
    for v in x:
      r |= Walk(v, act)
  if isinstance(x, dict):
    for k in x:
      r |= Walk(x[k], act)
  return r


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

  def CopyOfArgs(self):
    """Copying args is separated for profiling."""
    return {k: v for k, v in list(self.args_of.items())}

  def UpdateStructure(self, new_predicate):
    """Updates rules_of and args_of maps after extebded_rules update."""
    self.rules_of = parse.DefinedPredicatesRules(self.extended_rules)
    self.predicates = set(self.rules_of)
    self.direct_args_of = self.BuildDirectArgsOf()
    # Resetting args_of, to process the new predicates that were added.
    copied_args_of = self.CopyOfArgs()
    for predicate, args in copied_args_of.items():
      if new_predicate in args or new_predicate == predicate:
        del self.args_of[predicate]
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

  def BuildDirectArgsOfWalk(self, x, act):
    """Factored for profiling."""
    return Walk(x, act)

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
        if 'body' in rule:
          args |= self.BuildDirectArgsOfWalk(rule['body'], ExtractPredicateName)
        args |= self.BuildDirectArgsOfWalk(rule['head']['record'],
                                           ExtractPredicateName)
      direct_args_of[functor] = args
    return direct_args_of

  def ArgsOf(self, functor):
    """Arguments of functor. Retrieving from cache, or computing."""
      
    if functor not in self.args_of:
      built_args = self.BuildArgs(functor)
      # Args could be incomplete due to recursive calls.
      # Checking for that.
      building_me = 'building_' + functor
      if building_me in built_args:
        built_args = built_args - {building_me}
      if any(a.startswith('building_') for a in built_args):
        return (a for a in built_args if not a.startswith('building_'))
      self.args_of[functor] = built_args

    return self.args_of[functor]

  def BuildArgs(self, functor):
    """Returning all arguments of a functor."""
    if functor not in self.direct_args_of:
      # Assuming this is built-in or table.
      return set()

    self.args_of[functor] = {'building_' + functor}

    result = set()
    queue = collections.deque(self.direct_args_of[functor])
    while queue:
      e = queue.popleft()
      result.add(e)
      for a in self.ArgsOf(e):
        if a not in result:
          queue.append(a)

    del self.args_of[functor]

    return result

  def AllRulesOf(self, functor):
    """Returning all rules relevant to a predicate."""
    result = []
    if functor not in self.rules_of:
      return result
    result.extend(self.rules_of[functor])
    for f in self.args_of[functor]:
      if f == functor:
        raise FunctorError('Failed to eliminate recursion of %s.' % functor,
                           functor)
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
        # TODO: We should also remove predicates that become unused.
        if rule_predicate_name in args_map:
          continue
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
    Walk(rules, ReplacePredicate)
    self.extended_rules.extend(rules)
    self.UpdateStructure(name)

  def UnfoldRecursivePredicate(self, predicate, cover, depth, rules):   
    """Unfolds recurive predicate.""" 
    new_predicate_name = predicate + '_recursive'
    new_predicate_head_name = predicate + '_recursive_head'

    def ReplaceRecursivePredicate(x):
      if isinstance(x, dict) and 'predicate_name' in x:
        if x['predicate_name'] == predicate:
          x['predicate_name'] = new_predicate_name
      return []
    def ReplaceRecursiveHeadPredicate(x):
      if isinstance(x, dict) and 'predicate_name' in x:
        if x['predicate_name'] == predicate:
          x['predicate_name'] = new_predicate_head_name
      return []
    def ReplacerOfCoverMember(member):
      def Replace(x):
        if isinstance(x, dict) and 'predicate_name' in x:
          if x['predicate_name'] == member:
            x['predicate_name'] = member + '_recursive_head'
        return []
      return Replace

    for r in rules:
      if r['head']['predicate_name'] == predicate:
        r['head']['predicate_name'] = new_predicate_head_name
        Walk(r, ReplaceRecursivePredicate)
        for c in cover - {predicate}:
          Walk(r, ReplacerOfCoverMember(c))
      elif r['head']['predicate_name'] in cover:
        Walk(r, ReplaceRecursivePredicate)
        for c in cover - {predicate}:
          Walk(r, ReplacerOfCoverMember(c))
      elif (r['head']['predicate_name'][0] == '@' and
            r['head']['predicate_name'] != '@Make'):
        Walk(r, ReplaceRecursiveHeadPredicate)
        for c in cover - {predicate}:
          Walk(r, ReplacerOfCoverMember(c))        
      else:
        # This rule simply uses the predicate, keep the name.
        pass

    lib = recursion_library.GetRecursionFunctor(depth)
    lib = lib.replace('P', predicate)
    lib_rules = parse.ParseFile(lib)['rule']
    rules.extend(lib_rules)
    for c in cover - {predicate}:
      rename_lib = recursion_library.GetRenamingFunctor(c, predicate)
      rename_lib_rules = parse.ParseFile(rename_lib)['rule']
      rules.extend(rename_lib_rules)

  def UnfoldRecursions(self, depth_map):
    """Unfolds all recursions."""
    should_recurse, my_cover = self.RecursiveAnalysis(depth_map)
    new_rules = copy.deepcopy(self.rules)
    for p in should_recurse:
      depth = depth_map.get(p, {}).get('1', 8)
      self.UnfoldRecursivePredicate(p, my_cover[p], depth, new_rules)
    return new_rules

  def RecursiveAnalysis(self, depth_map):
    """Finds recursive cycles and predicates that would unfold them."""
    # TODO: Select unfolding predicates to guarantee unfolding.
    cover = []
    covered = set()
    deep = set(depth_map)
    for p, args in self.args_of.items():
      if p in args and p not in covered and '_MultBodyAggAux' not in p:
        c = {p}
        for p2 in args:
          if p in self.args_of[p2]:
            c.add(p2)
        cover.append(c)
        covered |= c

    my_cover = {}
    for c in cover:
      for p in c:
        my_cover[p] = c

    recursion_covered = set()
    should_recurse = []
    for c in cover:
      if c & deep:
        p = min(c & deep)
      else:
        p = min(c)
      should_recurse.append(p)
      recursion_covered |= my_cover[p]

    return should_recurse, my_cover