#!/usr/bin/python
#
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Copies the recursion tests into integration_tests/socratic, switching
every recursive component to mode: "socratic" and the engine to duckdb.
Goldens are not copied: the socratic runner points at the originals."""
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from parser_py import parse

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..')
TESTS = [
  'duckdb_diamond_abc_test', 'duckdb_diamond_fixpoint_tc_test',
  'duckdb_diamond_fixpoint_test', 'duckdb_diamond_stop_order_test',
  'duckdb_diamond_tc_test', 'duckdb_iteration_closure_test',
  'duckdb_smoothed_winmove_test', 'duckdb_stop_test',
  'psql_flow_test', 'psql_game_test', 'psql_graph_coloring_test',
  'psql_recursion_test', 'rec_cycle_test', 'rec_small_cycle_test',
  'sqlite_deep_recursion_test', 'sqlite_pagerank', 'sqlite_reachability',
  'sqlite_rec_depth', 'sqlite_rec_functor', 'sqlite_recursion',
  'sqlite_winmove_test', 'ultra_short_cycle_test', 'closure_test',
]


def PredicateNames(node, out):
  if isinstance(node, dict):
    if 'predicate_name' in node and isinstance(node['predicate_name'], str):
      out.add(node['predicate_name'])
    for v in node.values(): PredicateNames(v, out)
  elif isinstance(node, list):
    for v in node: PredicateNames(v, out)
  return out


def RecursivePredicates(text):
  """Predicates on a dependency cycle (one representative per SCC)."""
  rules = parse.ParseFile(text)['rule']
  deps = {}
  for r in rules:
    head = r['head']['predicate_name']
    if head.startswith('@'): continue
    body = PredicateNames(r.get('body', {}), set())
    body |= PredicateNames(r['head'].get('record', {}), set())
    deps.setdefault(head, set()).update(b for b in body if not b.startswith('@'))
  # Tarjan.
  index, low, stack, on, sccs, counter = {}, {}, [], set(), [], [0]
  def Visit(v):
    index[v] = low[v] = counter[0]; counter[0] += 1
    stack.append(v); on.add(v)
    for w in deps.get(v, ()):
      if w not in deps: continue
      if w not in index: Visit(w); low[v] = min(low[v], low[w])
      elif w in on: low[v] = min(low[v], index[w])
    if low[v] == index[v]:
      comp = []
      while True:
        w = stack.pop(); on.discard(w); comp.append(w)
        if w == v: break
      sccs.append(comp)
  for v in list(deps):
    if v not in index: Visit(v)
  return [sorted(c)[0] for c in sccs if len(c) > 1 or sorted(c)[0] in deps.get(sorted(c)[0], ())]


def Convert(name):
  text = open(os.path.join(SRC, name + '.l')).read()
  # Unannotated recursion runs to the engine's default depth: 8 for
  # sqlite/psql, 32 for duckdb. The copy keeps the original depth.
  default_depth = 32 if '@Engine("duckdb"' in text else 8
  text = re.sub(r'@Engine\("(sqlite|psql)"', '@Engine("duckdb"', text)
  annotated = set()
  def Rewrite(m):
    inner = m.group(1)
    pred = inner.split(',')[0].strip()
    annotated.add(pred)
    # Satellites iterate with their predicate: not annotated on their own.
    sat = re.search(r'satellites:\s*\[([^\]]*)\]', inner)
    if sat:
      annotated.update(x.strip() for x in sat.group(1).split(','))
    if 'mode:' in inner:
      inner = re.sub(r'mode:\s*"[a-z_]+"', 'mode: "socratic"', inner)
    else:
      inner += ', mode: "socratic"'
    return '@Recursive(%s)' % inner
  text = re.sub(r'@Recursive\(([^)]*)\)', Rewrite, text)
  extra = []
  for p in RecursivePredicates(text):
    if p not in annotated:
      extra.append('@Recursive(%s, %d, mode: "socratic");' % (p, default_depth))
  if extra:
    # After the @Engine line.
    lines = text.split('\n')
    at = next((i for i, l in enumerate(lines) if l.startswith('@Engine')), -1)
    lines[at + 1:at + 1] = extra
    text = '\n'.join(lines)
  with open(os.path.join(HERE, name + '.l'), 'w') as f:
    f.write(text)
  return extra


if __name__ == '__main__':
  for t in TESTS:
    extra = Convert(t)
    print('%-36s %s' % (t, ' '.join(extra) if extra else ''))
