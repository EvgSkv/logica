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

import datetime

class Timer:
  def __init__(self, name):
    self.name = name
    self.time = datetime.datetime.now()

  def Stop(self):
    print('%s / micros elapsed:' % self.name, (datetime.datetime.now() - self.time).microseconds)


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


def WalkWithTaboo(x, act, taboo):
  """Walking over a dictionary of lists, modifying and/or collecting info."""
  r = set()
  r |= set(act(x))
  if isinstance(x, list):
    for v in x:
      r |= WalkWithTaboo(v, act, taboo)
  if isinstance(x, dict):
    for k in x:
      if k not in taboo:
        r |= WalkWithTaboo(x[k], act, taboo)
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
    self.constant_literal_function = {}

    try:
      # This import takes about 500ms.
      import numpy
      numpy_is_here = True
    except:
      numpy_is_here = False
    if numpy_is_here:
      # This is faster sometimes.
      self.NumpyBuildArgsOf()
    for p in self.predicates:
      self.ArgsOf(p)

  def GetConstantFunction(self, value):
    if result := self.constant_literal_function.get(value):
      return result
    self.constant_literal_function[value] = (
      'LogicaCompilerConstant%d' % len(self.constant_literal_function))
    return self.constant_literal_function[value]

  def CopyOfArgs(self):
    """Copying args is separated for profiling."""
    return {k: v for k, v in list(self.args_of.items())}

  def UpdateStructure(self, new_predicate):
    """Updates rules_of and args_of maps after extebded_rules update."""
    self.rules_of = parse.DefinedPredicatesRules(self.extended_rules)
    self.predicates = set(self.rules_of)
    if new_predicate in self.rules_of:
      self.direct_args_of[new_predicate] = self.BuildDirectArgsOfPredicate(
        new_predicate)
    for p in self.rules_of:
      if p not in self.direct_args_of:
        self.direct_args_of[p] = self.BuildDirectArgsOfPredicate(p)

    # Resetting args_of, to process the new predicates that were added.
    copied_args_of = self.CopyOfArgs()
    for predicate, args in copied_args_of.items():
      if new_predicate in args or new_predicate == predicate:
        del self.args_of[predicate]
    for p in self.predicates:
      self.ArgsOf(p)
    # Uncomment for debuggin:

    # print('------------ Args Of:')
    # for k, v in self.args_of.items():
    #   print(k, '->', v)
    # print('Direct args Of:')
    # for k, v in self.direct_args_of.items():
    #   print(k, '->', v)


  def ParseMakeInstruction(self, predicate, instruction):
    """Parses Make instruction from syntax tree."""
    error_message = (
      'Bad functor call (aka @Make instruction):\n%s' % instruction)
    if '1' not in instruction or '2' not in instruction:
      raise FunctorError(error_message, predicate)
    if 'predicate_name' not in instruction['1']:
      raise FunctorError(error_message, predicate)
    applicant = instruction['1']['predicate_name']
    args_map = {}
    for arg_name, arg_value_dict in instruction['2'].items():
      if (
           (not isinstance(arg_value_dict, dict) or
            'predicate_name' not in arg_value_dict) and
           not isinstance(arg_value_dict, int) and
           not isinstance(arg_value_dict, str)):
        raise FunctorError(error_message, predicate)
      if isinstance(arg_value_dict, dict):
        args_map[arg_name] = arg_value_dict['predicate_name']
      else:
        args_map[arg_name] = self.GetConstantFunction(arg_value_dict)
    return predicate, applicant, args_map

  def Describe(self):
    return 'DirectArgs: %s,\nArgs: %s' % (self.direct_args_of, self.args_of)

  def BuildDirectArgsOfWalk(self, x, act):
    """Factored for profiling."""
    return Walk(x, act)

  def BuildDirectArgsOfPredicate(self, functor):
    args = set()
    rules = self.rules_of[functor]
    def ExtractPredicateName(x):
      if isinstance(x, dict) and 'predicate_name' in x:
        return [x['predicate_name']]
      return []
    for rule in rules:
      if 'body' in rule:
        args |= self.BuildDirectArgsOfWalk(rule['body'], ExtractPredicateName)
      args |= self.BuildDirectArgsOfWalk(rule['head']['record'],
                                          ExtractPredicateName)
    return args

  def BuildDirectArgsOf(self):
    """Builds a map of direct arguments of a functor."""
    direct_args_of = {}
    for functor in self.rules_of:
      direct_args_of[functor] = self.BuildDirectArgsOfPredicate(functor)
    return direct_args_of

  def NumpyBuildArgsOf(self):
    import numpy
    interesting_predicates = set(self.direct_args_of)
    directly_called_by = numpy.zeros(
      (len(interesting_predicates),
       len(interesting_predicates)))
    interesting_predicates_list = list(sorted(interesting_predicates))
    ipi = {  # Interesting predicate index.
      p: i for i, p in enumerate(interesting_predicates_list)}
    for p, args in self.direct_args_of.items():
      for a in args:
        if a in interesting_predicates:
          directly_called_by[ipi[a], ipi[p]] = 1
    a = directly_called_by
    while True:
      aa = (((a @ a) + a) > 0) * 1
      if (a == aa).all():
        break
      a = aa
    for i, p in enumerate(interesting_predicates_list):
      self.args_of[p] = set(self.direct_args_of[p])
      for j, v in enumerate(a[:, i]):
        if v:
          q = interesting_predicates_list[j]
          self.args_of[p].add(q)
          self.args_of[p] |= self.direct_args_of[q]

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
      args_of_e = self.ArgsOf(e)
      if isinstance(args_of_e, set):
        arg_type = 'final'
      else:
        arg_type = 'preliminary'

      for a in args_of_e:
        if a not in result:
          if arg_type == 'preliminary':
            queue.append(a)
          else:
            result.add(a)

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
            (self.args_of[applicant] & needs_building) or
            (set(args_map.values()) & needs_building)):
          continue
        self.Make(new_predicate, instruction)
        something_built = True
        needs_building.remove(name)
      if needs_building and not something_built:
        raise FunctorError('Could not resolve Make order.',
                           str(needs_building))
    surviving_rules = self.RemoveRulesProvenToBeNil(self.extended_rules)

    for value, function in self.constant_literal_function.items():
      if isinstance(value, int):
        self.extended_rules.append(parse.ParseRule(parse.HeritageAwareString('%s() = %d') %
                                   (function, value)))
      elif isinstance(value, str):
        self.extended_rules.append(parse.ParseRule(parse.HeritageAwareString('%s() = "%s"') %
                                   (function, value)))
      else:
        assert False, str((value, function))
    for p, c in surviving_rules.items():
      if c == 0:
        raise FunctorError('All rules contain nil for predicate %s. '
                           'Recursion unfolding failed.' % color.Warn(p), p)

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
                            '@NoInject', '@Iteration']:
        continue
      for rule in rules:
        if ('literal' not in
            rule['head']['record']['field_value'][0]['value']['expression'] or
            'the_predicate' not in
            rule['head']['record']['field_value'][0]['value']['expression'][
              'literal']):
          raise FunctorError('This annotation requires predicate symbol '
                             'as the first positional argument.',
                             rule['full_text'])

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
    
  def UnfoldRecursivePredicateFlatFashion(self, cover, depth, rules,
                                          iterative, ignition_steps, stop):
    visible = lambda p: '_MultBodyAggAux' not in p
    simplified_cover = {c for c in cover if visible(c)}
    direct_args_of = {c: [] for c in cover if visible(c)}
    for p, args in self.direct_args_of.items():
      if p in simplified_cover:
        for a in args:
          if a in cover:
            if visible(a):
              direct_args_of[p].append(a)
            else:
              for a2 in self.direct_args_of[a]:
                if a2 in cover:
                  direct_args_of[p].append(a2)
    def ReplacePredicate(original, new):
      def Replace(x):
        if isinstance(x, dict) and 'predicate_name' in x:
          if x['predicate_name'] == original:
            x['predicate_name'] = new
        return []
      return Replace
    for r in rules:
      if r['head']['predicate_name'] in cover:
        p = r['head']['predicate_name']
        if visible(p):
          r['head']['predicate_name'] = p + '_ROne'
        for c in simplified_cover:
          Walk(r, ReplacePredicate(c, c + '_RZero'))
      elif (r['head']['predicate_name'][0] == '@' and
            r['head']['predicate_name'] != '@Make'):
        for c in cover:
          Walk(r, ReplacePredicate(c, c + '_ROne'))

    if iterative:
      lib = recursion_library.GetFlatIterativeRecursionFunctor(
        depth, simplified_cover, direct_args_of,
        ignition_steps, stop)
    else:
      lib = recursion_library.GetFlatRecursionFunctor(
        depth, simplified_cover, direct_args_of)

    lib_rules = parse.ParseFile(lib)['rule']
    rules.extend(lib_rules)


  def UnfoldRecursivePredicate(self, predicate, cover, depth, rules):   
    """Unfolds recurive predicate.""" 
    new_predicate_name = predicate + '_recursive'
    new_predicate_head_name = predicate + '_recursive_head'

    def ReplacePredicate(original, new):
      def Replace(x):
        if isinstance(x, dict) and 'predicate_name' in x:
          if x['predicate_name'] == original:
            x['predicate_name'] = new
        return []
      return Replace

    def ReplacerOfRecursivePredicate():
      return ReplacePredicate(predicate, new_predicate_name)

    def ReplacerOfRecursiveHeadPredicate():
      return ReplacePredicate(predicate, new_predicate_head_name)

    def ReplacerOfCoverMember(member):
      return ReplacePredicate(member, member + '_recursive_head')

    for r in rules:
      if r['head']['predicate_name'] == predicate:
        r['head']['predicate_name'] = new_predicate_head_name
        Walk(r, ReplacerOfRecursivePredicate())
        for c in cover - {predicate}:
          Walk(r, ReplacerOfCoverMember(c))
      elif r['head']['predicate_name'] in cover:
        Walk(r, ReplacerOfRecursivePredicate())
        for c in cover - {predicate}:
          Walk(r, ReplacerOfCoverMember(c))
      elif (r['head']['predicate_name'][0] == '@' and
            r['head']['predicate_name'] != '@Make'):
        Walk(r, ReplacerOfRecursiveHeadPredicate())
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

  def GetStop(self, depth_map, p):
    stop = depth_map.get(p, {}).get('stop')
    if isinstance(stop, dict):
      stop = stop['predicate_name']
    return stop

  def UnfoldRecursions(self, depth_map, default_iterative, default_depth):
    """Unfolds all recursions."""
    should_recurse, my_cover = self.RecursiveAnalysis(
      depth_map, default_iterative, default_depth)
    new_rules = copy.deepcopy(self.rules)
    for p, style in should_recurse.items():
      depth = depth_map.get(p, {}).get('1', default_depth)
      if style == 'vertical':
        self.UnfoldRecursivePredicate(p, my_cover[p], depth, new_rules)
      elif style == 'horizontal' or style == 'iterative_horizontal':
        # Old ad-hoc formula:
        # ignition = len(my_cover[p]) * 3 + 4
        # Calculation of ignition:
        #   len(cover) to fill all predicates,
        #   + 2 for iterations
        #   + 1 for final step.
        ignition = len(my_cover[p]) + 3
        if ignition % 2 == depth % 2:
          ignition += 1
        stop = self.GetStop(depth_map, p)
        if stop and stop not in my_cover[p]:
          raise FunctorError(
            color.Format(
              'Recursive predicate {warning}{p}{end} uses stop signal '
              '{warning}{stop}{end} that '
              'does not exist or is outside of the recurvisve component.'
              ' This means that {warning}{stop}{end} does not depend '
              'on {warning}{p}{end} which means it would not change over '
              'iteration. There is a bug in rules, or you need to specify '
              '{warning}satellites{end} of {warning}{p}{end} which should run '
              'in the iteration as well and which {warning}{stop}{end} '
              'monitors.',
              {'p': p, 'stop': stop}), p)
        self.UnfoldRecursivePredicateFlatFashion(
          my_cover[p], depth, new_rules,
          iterative=(style=='iterative_horizontal'),
          # Ignition is my_cover[p] * 3 because it may take my_cover[p] steps
          # to propagate dependency. So we have initial stage, iteration and final
          # propagation to outputs. Plus 5 to cover small numbers.
          ignition_steps=depth_map.get(p, {}).get('ignition', ignition),
          stop=stop)
      else:
        assert False, 'Unknown recursion style:' + style
    return new_rules

  def RemoveRulesProvenToBeNil(self, rules):
    proven_to_be_nothing = set({'nil'})
    def ReplacePredicate(original, new):
      def Replace(x):
        if isinstance(x, dict) and 'predicate_name' in x:
          if x['predicate_name'] == original:
            x['predicate_name'] = new
        return []
      return Replace
    class NilCounter:
      def __init__(self):
        self.nil_count  = 0
      def CountNils(self, node):
        if isinstance(node, dict):
          if 'predicate_name' in node:
            if node['predicate_name'] in proven_to_be_nothing:
              self.nil_count += 1
        return []
    defined_predicates = {rule['head']['predicate_name']
                          for rule in rules}
    while True:
      rules_per_predicate = {}
      for rule in rules:
        p = rule['head']['predicate_name']
        c = NilCounter()
        WalkWithTaboo(rule, c.CountNils,
                      # Do not walk into:
                      #   predicate value literals,
                      #   combine expressions because they will be trivially
                      #     null,
                      #   lists of satelites.
                      taboo=['the_predicate', 'combine', 'satellites'])
        rules_per_predicate[p] = rules_per_predicate.get(p,0) + (
          c.nil_count == 0)
      is_nothing = set()
      for p in defined_predicates:
        if rules_per_predicate[p] == 0:
          is_nothing |= {p}
      if is_nothing <= proven_to_be_nothing:
        break
      proven_to_be_nothing |= is_nothing
    for p in proven_to_be_nothing - {'nil'}:
      for rule in rules:
        if rule['head']['predicate_name'] == p:
          rule['head']['predicate_name'] = 'Nullified' + p
        elif not rule['head']['predicate_name'].startswith('@'):
          Walk(rule, ReplacePredicate(p, 'nil'))
      if '_' not in p:
        raise FunctorError(
          color.Format(
            'Predicate {warning}{p}{end} was proven to be empty. '
            'Most likely initial base condition of recursion is missing, or '
            'flat recursion is not given enough steps.',
            {'p': p}), p)
      del rules_per_predicate[p]
    self.UpdateStructure(p)
    return rules_per_predicate

  def IsCutOfCover(self, p, cover_leaf):
    """Determining if p cuts the cover leaf into non-recursive state."""
    stack = [(p, set())]
    cover_leaf = set(cover_leaf)
    while stack:
      t, u = stack.pop()
      if t in u:
        return False
      for x in cover_leaf & self.direct_args_of[t]:
        if x != p:
          stack.append((x, (u | {t})))
    return True

  def RecursiveAnalysis(self, depth_map, default_iterative, default_depth):
    """Finds recursive cycles and predicates that would unfold them."""
    # TODO: Select unfolding predicates to guarantee unfolding.
    cover = []
    covered = set()
    deep = set(depth_map)
    for p, args in self.args_of.items():
      # TODO: We probably don't need _MultBodyAggAux exception.
      if p in args and p not in covered and '_MultBodyAggAux' not in p:
        c = {p}
        for p2 in args:
          if p2 in self.args_of and p in self.args_of[p2]:
            c.add(p2)
        cover.append(c)
        covered |= c

    my_cover = {}
    for c in cover:
      for p in c:
        my_cover[p] = c

    recursion_covered = set()
    should_recurse = {}
    for c in cover:
      if c & deep:
        p = min(c & deep)
      else:
        p = min(c)
      if depth_map.get(p, {}).get('1', default_depth) == -1:
        depth_map[p]['1'] = 1000000000
      # Iterate if explicitly requested or unspecified
      # and number of steps is greater than 20.
      if (depth_map.get(p, {}).get('iterative', default_iterative) or
          depth_map.get(p, {}).get('iterative', True) == True and
          depth_map.get(p, {}).get('1', default_depth) > 20):
        should_recurse[p] = 'iterative_horizontal'
      elif self.IsCutOfCover(p, c):
        should_recurse[p] = 'vertical'
      else:
        should_recurse[p] = 'horizontal'
      recursion_covered |= my_cover[p]
    # Tried adding stop signal to recursive component, but it feels
    # unnatural.
    # if p in should_recurse:
    #   if stop := self.GetStop(depth_map, p):
    #     my_cover[p].add(stop)
    #     my_cover[stop] = my_cover[p]
    # print('my cover:', my_cover)
    return should_recurse, my_cover