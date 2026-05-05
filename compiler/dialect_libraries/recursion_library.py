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

def DiamondOrder(cover, direct_args_of, main, stop):
  """Order of cover members for one diamond iteration.

  Main goes first (its in-cover dependencies inevitably read previous
  iteration). Stop goes after main to see incremental difference of
  main. The rest is filled greedily, each time picking the predicate
  with the highest fraction of in-cover dependencies already computed in
  this iteration. Lexicographic name as tiebreak — fully deterministic.
  """
  cover = set(cover)
  order = [main, stop] if stop else [main]
  done = set(order)
  remaining = cover - done
  while remaining:
    def fraction(p):
      deps = set(direct_args_of[p]) & cover
      if not deps:
        return 1.0
      return len(deps & done) / len(deps)
    chosen = min(remaining, key=lambda p: (-fraction(p), p))
    order.append(chosen)
    done.add(chosen)
    remaining -= {chosen}
  return order


def BuildTypeReprPortalRule(portal_name, source_predicate, head_record):
  """Generate: portal_name(a: TypeRepr("src", "a"), ...) :- 1 = 0;"""
  parts = []
  has_value = False
  for fv in head_record['field_value']:
    f = fv['field']
    if f == 'logica_value':
      has_value = True
      continue
    repr_expr = 'TypeRepr("%s", "%s")' % (source_predicate, f)
    if isinstance(f, int):
      parts.append(repr_expr)
    else:
      parts.append('%s: %s' % (f, repr_expr))
  args = '(%s)' % ', '.join(parts) if parts else '()'
  value_part = ''
  if has_value:
    value_part = ' = TypeRepr("%s", "logica_value")' % source_predicate
  return '%s%s%s :- 1 = 0;' % (portal_name, args, value_part)


def GetDiamondRecursionFunctor(cover, direct_args_of, main,
                               repetitions, stop,
                               head_records=None):
  """Diamond recursion: in-place rewrite, single flat iteration step.

  p_diamond is the iteration target: it carries the cover member's actual
  rules, is @Ground'd in place, and @Iteration loops over the p_diamond's
  in DiamondOrder. Bodies of p_diamond read p_portal (a phantom externally
  grounded to p_diamond's own table) — this breaks the @Make cycle while
  letting the in-place rewrite see the freshest values written by earlier
  members of the same iteration step.

  After the iteration completes, p is computed as one final Gauss-Seidel
  pass on top of the iterated tables, with the same order rule: a
  predicate that comes earlier in DiamondOrder reads from the freshly
  computed p (the post-iteration step), a self-reference or a later
  predicate reads from the iterated p_diamond. This way the natural
  compile-time edges (p_diamond -> p, earlier_p -> later_p) put p strictly
  after the whole iteration in the topo order.

  Example.
  # Original ring A->B->C->A, DiamondOrder = [A, B, C]:
  @Ground(A_portal);
  @Ground(A_diamond, A_portal);
  @Ground(B_portal);
  @Ground(B_diamond, B_portal);
  @Ground(C_portal);
  @Ground(C_diamond, C_portal);
  A_portal(<fields>: TypeRepr("A", "<field>"), ...) :- 1 = 0;
  B_portal(<fields>: TypeRepr("B", "<field>"), ...) :- 1 = 0;
  C_portal(<fields>: TypeRepr("C", "<field>"), ...) :- 1 = 0;
  A_diamond := A_ROne(A_RZero: A_portal, B_RZero: B_portal, C_RZero: C_portal);
  B_diamond := B_ROne(A_RZero: A_portal, B_RZero: B_portal, C_RZero: C_portal);
  C_diamond := C_ROne(A_RZero: A_portal, B_RZero: B_portal, C_RZero: C_portal);
  A := A_ROne(A_RZero: A_diamond, B_RZero: B_diamond, C_RZero: C_diamond);
  B := B_ROne(A_RZero: A,         B_RZero: B_diamond, C_RZero: C_diamond);
  C := C_ROne(A_RZero: A,         B_RZero: B,         C_RZero: C_diamond);
  @Iteration(A_diamond_iter,
             predicates: [A_diamond, B_diamond, C_diamond],
             repetitions: <N>);
  """
  cover = set(cover)
  order = DiamondOrder(cover, direct_args_of, main, stop)

  if not stop and repetitions == 1000000000:  # 1000000000 = ∞.
    stop = main + '_fixpoint'

  position = {p: i for i, p in enumerate(order)}
  stop_file_name = ''
  if stop:
    stop_file_name = '/tmp/logical_stop_%s_%s.json' % (
      str(time.time()).replace('.', ''), stop)
  result_rules = []
  # Ground the diamond predicates (in place) and route input phantoms to
  # the same table by name — no literal-string table_name juggling.
  for p in order:
    if stop and stop == p:
      maybe_copy_to_file = ', copy_to_file: "%s"' % stop_file_name
    else:
      maybe_copy_to_file = ''
    result_rules.append(f'@Ground({p}_portal);')
    result_rules.append(
      f'@Ground({p}_diamond, {p}_portal{maybe_copy_to_file});')
  if head_records:
    for p in order:
      if p in head_records:
        result_rules.append(
          BuildTypeReprPortalRule(p + '_portal', p, head_records[p]))
  for p in order:
    args = ', '.join(f'{a}_RZero: {a}_portal'
                     for a in sorted(set(direct_args_of[p]) & cover))
    result_rules.append(f'{p}_diamond := {p}_ROne({args});')
  # Final Gauss-Seidel pass: for predicate p at position i in DiamondOrder,
  # bind a_RZero to the freshly computed a if a is earlier in the order,
  # otherwise (self or later) to a_diamond. Compile naturally produces
  # edges p_diamond -> p and earlier_p -> later_p, so concertina puts p
  # strictly after the iteration and orders the final pass deterministically.
  for p in order:
    args = []
    for a in sorted(set(direct_args_of[p]) & cover):
      if position[a] < position[p]:
        args.append(f'{a}_RZero: {a}')
      else:
        args.append(f'{a}_RZero: {a}_diamond')
    result_rules.append(f'{p} := {p}_ROne({", ".join(args)});')

  # For optional fixpoint detection:
  recurring_list = [f'{p}_diamond' for p in order]

  if stop == main + '_fixpoint':
    result_rules.append(f'@Ground({main}_before);')
    result_rules.append(f'@Ground({stop}, copy_to_file: "{stop_file_name}");')
    result_rules.append('{main}_before(..r) :- {main}_portal(..r);'.format(main=main))
    fixpoint_rule = (
      'MAIN_fixpoint() :- '
      'Array{ r -> r :- MAIN_before(..r)} == Array{ r -> r :- MAIN_diamond(..r)};')
    fixpoint_rule = fixpoint_rule.replace('MAIN', main)
    result_rules.append(fixpoint_rule)
    recurring_list = [main + '_before'] + recurring_list + [stop]

  iter_predicates = ', '.join(recurring_list)

  maybe_stop = ''
  if stop:
    maybe_stop = ', stop_signal: "%s"' % stop_file_name
  result_rules.append(
    f'@Iteration({main}_diamond_iter, predicates: [{iter_predicates}], '
    f'repetitions: {repetitions}, mode: "diamond"{maybe_stop});')
  return '\n'.join(result_rules)


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
