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

"""Runs the recursion tests under Socrates against the original goldens.

python3 integration_tests/socratic/run_tests.py [name ...]"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from common import color
from common import logica_test

# (test, source, golden) — the golden is the original test's golden.
TESTS = [
  ('duckdb_diamond_abc_test', None, None),
  ('duckdb_diamond_fixpoint_tc_test', None, None),
  ('duckdb_diamond_fixpoint_test', None, None),
  # duckdb_diamond_stop_order_test: N grows forever, only its stop predicate
  # ends the SQL iteration; Socrates runs to a fixpoint that does not exist.
  # duckdb_diamond_tc_test: PrevTC() Array= ... is an array aggregate in
  # the recursive component.
  # duckdb_iteration_closure_test: its golden is for mode: "iterative";
  # the diamond (and socratic) answer is 96.
  ('duckdb_smoothed_winmove_test', None, None),
  ('duckdb_stop_test', None, None),
  ('duckdb_flow_test', 'psql_flow_test', None),
  ('psql_game_test', None, None),
  ('duckdb_graph_coloring_test', 'psql_graph_coloring_test', None),
  ('duckdb_recursion_test', 'psql_recursion_test', None),
  # rec_cycle_test: expects bag duplicates (g repeated 259 times);
  # Socrates relations are sets.
  ('rec_small_cycle_test', None, None),
  # sqlite_deep_recursion_test: the duckdb/diamond conversion itself gives
  # N = M = 1001 (functor copy), so the golden is not reachable here.
  ('sqlite_pagerank', None, None),
  ('sqlite_reachability', None, None),
  # sqlite_rec_depth: fails in SQL diamond mode too (distinct mix).
  ('sqlite_rec_functor', None, None),
  ('sqlite_recursion', None, None),
  ('sqlite_winmove_test', None, None),
  # ultra_short_cycle_test: expects bag duplicates (Q repeated 9 times);
  # Socrates relations are sets.
]


def main():
  """Each test runs in its own process: a crash is a result, not the end."""
  import subprocess
  wanted = set(sys.argv[1:])
  root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
  for name, src, golden in TESTS:
    if wanted and name not in wanted:
      continue
    code = (
        "from common import logica_test\n"
        "logica_test.TestManager.RunTest('socratic/%s', "
        "src='integration_tests/socratic/%s.l', golden='integration_tests/%s.txt', "
        "predicate='Test', user_flags=None, use_concertina=True)\n"
        % (name, src or name, golden or name))
    env = dict(os.environ, LOGICA_PARSER=os.environ.get('LOGICA_PARSER', 'CPP'))
    import re
    try:
      r = subprocess.run([sys.executable, '-c', code], cwd=root, env=env,
                         capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
      print('%-40s TIMEOUT (2 min)' % name, flush=True)
      continue
    out = re.sub(r'\x1b\[[0-9;]*m', '', r.stdout + r.stderr)
    if 'PASSED' in out:
      status = '{ok}PASSED{end}'
    elif 'FAILED' in out:
      status = '{error}FAILED{end} (golden differs)'
    else:
      m = (re.search(r'\[ Error \] (.*)', out) or re.search(r'socrates: (.*)', out) or
           re.search(r'^(\w*(?:Error|Exception)\b.*)$', out, re.M))
      reason = m.group(1).strip() if m else 'exit %d: %s' % (r.returncode, out.strip().split('\n')[-1][:100])
      status = '{warning}ERROR{end} ' + reason[:140].replace('{', '{{').replace('}', '}}')
    print(color.Format('% 50s   %s' % (name, status)), flush=True)


if __name__ == '__main__':
  main()
