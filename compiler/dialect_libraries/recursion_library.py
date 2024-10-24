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

import time

def GetRecursionFunctor(depth):
  """Returns functor that unfolds recursion.

  Example:
  P_r0 := P_recursive_head(P_recursive: nil);
  P_r1 := P_recursive_head(P_recursive: P_r0);
  P_r2 := P_recursive_head(P_recursive: P_r1);
  P_r3 := P_recursive_head(P_recursive: P_r2);
  P := P_r3();
  """
  result_lines = ['P_r0 := P_recursive_head(P_recursive: nil);']
  for i in range(depth):
      result_lines.append(
          'P_r{1} := P_recursive_head(P_recursive: P_r{0});'.format(i, i + 1))
  result_lines.append('P := P_r{0}();'.format(depth))
  return '\n'.join(result_lines)

def GetRenamingFunctor(member, root):
  """Renaming recursive cover member.

  Example.
  # Original:
  A(x) :- B(x);
  B(x) :- C(x);
  C(x) :- D(x);
  D(x) :- A(x);
  D(0);

  # After first renaming.
  D_recursive_head(x) :- A_recursive(x);
  D_recursive_head(0);

  C_recursive_head(x) :- D_recursive_head(x);

  B_recursive_head(x) :- C_recursive_head(x);

  A_recursive_head(x) :- B_recursive_head(x);

  A := A_r10();
  D := D_recursive_head(A_recursive: A);  # <-- renaming functor.
  C := C_recursive_head(A_recursive: A);
  B := B_recursive_head(A_recursive: A);
  """
  return '{0} := {0}_recursive_head({1}_recursive: {1});'.format(member, root)

def GetFlatRecursionFunctor(depth, cover, direct_args_of):
  """Doing the whole flat recursion.

  Example.
  # Original:
  A() Max= 1;
  B() Max= 1;
  A() Max= A() + B();
  B() Max= A() * B();

  # Recursion unfolding functors:
  A_fr0 := A_ROne(A_RZero: nil, B_RZero: nil);
  A_fr1 := A_ROne(A_RZero: A_fr0, B_RZero: B_fr0);
  A_fr2 := A_ROne(A_RZero: A_fr1, B_RZero: B_fr1);
  A_fr3 := A_ROne(A_RZero: A_fr2, B_RZero: B_fr2);
  A := A_fr3();
  B_fr0 := B_ROne(A_RZero: nil, B_RZero: nil);
  B_fr1 := B_ROne(A_RZero: A_fr0, B_RZero: B_fr0);
  B_fr2 := B_ROne(A_RZero: A_fr1, B_RZero: B_fr1);
  B_fr3 := B_ROne(A_RZero: A_fr2, B_RZero: B_fr2);
  B := B_fr3();
  """
  result_rules = []
  for p in sorted(cover):
    for i in range(depth + 1):
      args = []
      for a in sorted(set(direct_args_of[p]) & cover):
        v = 'nil'
        if i > 0:
          v = f'{a}_fr{i - 1}'
        args.append(f'{a}_RZero: {v}')
      args_str = ', '.join(args)
      rule = f'{p}_fr{i} := {p}_ROne({args_str});'
      result_rules.append(rule)
    rule = f'{p} := {p}_fr{depth}();'
    result_rules.append(rule)
  program = '\n'.join(result_rules)
  return program

def GetFlatIterativeRecursionFunctor(depth, cover, direct_args_of,
                                     ignition_steps, stop):
  """Doing the whole flat recursion.

  Example.
  # Original:
  A() Max= 1;
  B() Max= 1;
  A() Max= A() + B();
  B() Max= A() * B();

  # Recursion unfolding functors:
  A_ifr0 := A_ROne(A_RZero: nil, B_RZero: nil);
  A_ifr1 := A_ROne(A_RZero: A_ifr0, B_RZero: B_ifr0);
  A_ifr2 := A_ROne(A_RZero: A_ifr1, B_RZero: B_ifr1);
  A_ifr3 := A_ROne(A_RZero: A_ifr2, B_RZero: B_ifr2);
  @Ground(A_ifr0);
  @Ground(A_ifr1);
  @Ground(A_ifr2, A_ifr0);
  @Ground(A_ifr3);
  A := A_ifr3();
  B_ifr0 := B_ROne(A_RZero: nil, B_RZero: nil);
  B_ifr1 := B_ROne(A_RZero: A_ifr0, B_RZero: B_ifr0);
  B_ifr2 := B_ROne(A_RZero: A_ifr1, B_RZero: B_ifr1);
  B_ifr3 := B_ROne(A_RZero: A_ifr2, B_RZero: B_ifr2);
  @Ground(B_ifr0);
  @Ground(B_ifr1);
  @Ground(B_ifr2, B_ifr0);
  @Ground(B_ifr3);
  B := B_ifr3();
  @Iteration(IterateA, predicates: ["A_ifr1", "A_ifr2", "B_ifr1", "B_ifr2"], repetitions: 4);
  """
  result_rules = []
  iterate_over_upper_half = []
  iterate_over_lower_half = []
  # inset = ignition_steps // 2
  inset = 2
  stop_file_name = ''
  if stop:
    stop_file_name = '/tmp/logical_stop_%s_%s.json' % (
      str(time.time()).replace('.', ''),
      stop)
  for p in sorted(cover):
    for i in range(ignition_steps):
      args = []
      for a in sorted(set(direct_args_of[p]) & cover):
        v = 'nil'
        if i > 0:
          v = f'{a}_ifr{i - 1}'
        args.append(f'{a}_RZero: {v}')
      args_str = ', '.join(args)
      rule = f'{p}_ifr{i} := {p}_ROne({args_str});'
      result_rules.append(rule)
      if stop and stop == p:
        maybe_copy_to_file = ', copy_to_file: "%s"' % stop_file_name
      else:
        maybe_copy_to_file = ''
      if i != ignition_steps - inset: 
        result_rules.append(
          f'@Ground({p}_ifr{i}{maybe_copy_to_file});')
      else:
        result_rules.append(
          f'@Ground({p}_ifr{i}, {p}_ifr{i - 2}{maybe_copy_to_file});')

    iterate_over_upper_half += [f'{p}_ifr{ignition_steps - inset - 1}']
    iterate_over_lower_half += [f'{p}_ifr{ignition_steps - inset}']

    rule = f'{p} := {p}_ifr{ignition_steps - 1}();'

    result_rules.append(rule)

  iterate_over = iterate_over_upper_half + iterate_over_lower_half
  iterate_over_str = ', '.join(p for p in iterate_over)
  maybe_stop = ''
  if stop:
    maybe_stop = ', stop_signal: "%s"' % stop_file_name
  rule = f'@Iteration({min(cover)}, predicates: [{iterate_over_str}], repetitions: {(depth + 1 - ignition_steps) // 2 + 1}{maybe_stop});'
  result_rules.append(rule)

  program = '\n'.join(result_rules)
  return program
