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

# Python representation of Logica propositions, expressions and rules.
# Example usage:
# P = avatar.Predicate('P')
# T = avatar.Predicate('T')
# F = avatar.Predicate('F')
# x, y, z = avatar.Variables('x', 'y', 'z')
# Aggr = avatar.Aggregation
# print(+P(a=x, b=Aggr('List', y), c = F(x=y)) << T(x, y, z=x))
#
# Prints:
# P(a: x, b? List= y, c: F(x: y)) distinct :- T(x, y, z: x)

class LogicalTerm:
  """Proposition or expression."""
  @classmethod
  def FromSyntax(cls, syntax):
    if 'call' in syntax:
      p = Predicate(syntax['call']['predicate_name'])
      positional_args = []
      named_args = {}
      for fv in syntax['call']['record']['field_value']:
        value = cls.FromSyntax(fv['value']['expression'])
        if isinstance(fv['field'], int):
          positional_args[fv['field']:fv['field']] = [value]
        else:
          named_args[fv['field']] = value
      return p(*positional_args, **named_args)

    if 'literal' in syntax:
      literal = syntax['literal']
      if 'the_number' in literal:
        number_str = literal['the_number']['number']
        if '.' in number_str:
          return Literal(float(number_str))
        return Literal(int(number_str))
      if 'the_string' in literal:
        return Literal(literal['the_string']['the_string'])
      if 'the_list' in literal:
        return Literal([LogicalTerm.FromSyntax(e)
                                for e in literal['the_list']['element']])
      assert False, syntax

    assert False, syntax


class Literal(LogicalTerm):
  def __init__(self, value):
    self.value = value
  
  def __str__(self):
    def Render(x):
      if isinstance(x, int) or isinstance(x, float):
        return str(x)
      if isinstance(x, list):
        return '[%s]' % ', '.join(map(Render, x))
      if isinstance(x, dict):
        return '{%s}' % ', '.join('%s: %s' % (k, Render(v))
                                  for k, v in x.items())
      if isinstance(x, str):
        assert '"' not in x, x
        assert '\\' not in x, x
        return '"%s"' % x
      if isinstance(x, LogicalTerm):
        return str(x)
      assert False, x
    return Render(self.value)

  def AsJson(self):
    value = self.value
    if (isinstance(value, int) or
        isinstance(value, float) or
        isinstance(value, str)):
      return value
    if isinstance(value, list):
      return [x.AsJson() for x in value]
    if isinstance(value, dict):
      return {k: v.AsJson() for k, v in value}
    assert False

class PredicateCall(LogicalTerm):
  def __init__(self, predicate_name,
               positional_args, named_args,
               distinct_denoted=None):
    def Digest(x):
      if (isinstance(x, int) or isinstance(x, float) or
          isinstance(x, list) or isinstance(x, dict)):
        return Literal(x)
      return x
    self.predicate_name = predicate_name
    self.positional_args = list(map(Digest, positional_args))
    self.named_args = {k: Digest(v) for k, v in named_args.items()}
    self.names_aggregated = [name
                             for name in self.named_args
                             if isinstance(self.named_args[name], Aggregation)]
    self.distinct_denoted = distinct_denoted

  def __pos__(self):
    return PredicateCall(self.predicate_name, self.positional_args, self.named_args,
                         True)

  def __str__(self):
    def RenderKeyValue(k, v):
      if k in self.names_aggregated:
        return '%s? %s= %s' % (
          k, v.aggregating_operator, v.aggregated_expression
        )
      if isinstance(v, Variable) and k == v.name:
        return '%s:' % k
      return '%s: %s' % (k, v)
    assert self.distinct_denoted or not self.names_aggregated, (
      self.predicate_name, self.positional_args, self.named_args,
      self.names_aggregated, self.distinct_denoted)

    for x in list(self.positional_args) + list(self.named_args.values()):
      assert isinstance(x, LogicalTerm), x

    positional = ', '.join(map(str, self.positional_args))
    named = ', '.join(RenderKeyValue(k, v)
                      for k, v in self.named_args.items())
    t = filter(None, [positional, named])
    distinct_str = ' distinct' if self.distinct_denoted else ''
    return '%s(%s)%s' % (self.predicate_name, ', '.join(t),
                         distinct_str)
  
  def __lshift__(self, body):
    return Rule(self, body)

  def __and__(self, other_conjunct):
    if isinstance(other_conjunct, Conjunction):
      return Conjunction([self] + other_conjunct.conjuncts)
    return Conjunction([self, other_conjunct])

  def __call__(self, *positional_args, **named_args):
    new_positional_args = self.positional_args
    new_positional_args[0:len(positional_args)] = positional_args
    new_named_args = dict(list(self.named_args.items()) +
                          list(named_args.items()))
    return PredicateCall(self.predicate_name,
                         new_positional_args, new_named_args)


class Subscript(LogicalTerm):
  def __init__(self, record, field):
    self.record = record
    self.field = field
  
  def __str__(self):
    return '%s.%s' % (self.record, self.field)

class Rule:
  def __init__(self, head: PredicateCall, body):
    self.head = head
    self.body = body
    self.comment_before_rule : str = None
  
  def __str__(self):
    if self.comment_before_rule:
      comment = '# ' + '# '.join(self.comment_before_rule.split('\n')) + '\n'
    else:
      comment = ''
    if self.body:
      return '%s%s :- %s' % (comment, self.head, self.body) 
    else:
      return comment + str(self.head)

class Conjunction(LogicalTerm):
  def __init__(self, conjuncts):
    self.conjuncts = conjuncts
  
  def __str__(self):
    return '\n  ' + ',\n  '.join(map(str, self.conjuncts))

  def __and__(self, other_conjunct):
    if isinstance(other_conjunct, Conjunction):
      return Conjunction(self.conjuncts + other_conjunct.conjuncts)
    return Conjunction(self.conjuncts + [other_conjunct])

class Disjunction(LogicalTerm):
  def __init__(self, disjuncts):
    self.disjuncts = disjuncts

  def __str__(self):
    return '\n  ' + ' |\n  '.join(map(lambda x: '(%s)' % x, self.disjuncts))

  def __or__(self, other_disjunct):
    if isinstance(other_disjunct, Disjunction):
      return Disjunction(self.disjuncts + other_disjunct.disjuncts)
    return Disjunction(self.disjuncts + [other_disjunct])


class Variable(LogicalTerm):
  def __init__(self, name):
    self.name = name
  
  def __str__(self):
    return self.name


def Variables(*variables):
  return map(Variable, variables)


class Aggregation(LogicalTerm):
  def __init__(self, aggregating_operator, aggregated_expression):
    self.aggregating_operator = aggregating_operator
    self.aggregated_expression = aggregated_expression

class Predicate:
  def __init__(self, predicate_name):
    self.predicate_name = predicate_name
  
  def __call__(self, *args, **named_args):
    return PredicateCall(self.predicate_name, args, named_args)

class Program:
  def __init__(self, rules):
    self.rules = rules
  
  def AddRule(self, rule):
    self.rules.append(rule)
  
  def __str__(self):
    return ';\n\n'.join(map(str, self.rules))
  