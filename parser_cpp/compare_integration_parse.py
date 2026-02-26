#!/usr/bin/env python3

# Copyright 2026 The Logica Authors
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

"""Compare C++ parser output vs python logica.py parse on integration tests.

Runs on all integration_tests/*.l files and compares JSON ASTs.
Output format is intentionally similar to common/logica_test.py.

Usage:
  python3 parser_cpp/compare_integration_parse.py
  python3 parser_cpp/compare_integration_parse.py test_only=duckdb_json_test,closure_test
  python3 parser_cpp/compare_integration_parse.py strict_errors
  python3 parser_cpp/compare_integration_parse.py show_timings

Notes:
- Assumes repo root as working directory.
- Honors LOGICAPATH environment variable for both parsers.
- Uses in-process parsing for both modes by temporarily setting LOGICA_PARSER.
- By default, tests PASS if both parsers fail (same success/failure). Use strict_errors
  to require identical stderr on failing parses.
"""

from __future__ import annotations

import contextlib
import difflib
import glob
import json
import os
import sys
import time
import traceback
from typing import Any, List, Tuple


# Ensure repo root is importable even when running this script from a subdir.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
  sys.path.insert(0, REPO_ROOT)

# Allow running as a script from repo root.
if __name__ == '__main__' and not __package__:
  from common import color
  from parser_py import parse
else:
  from ..common import color
  from ..parser_py import parse


RUN_ONLY: List[str] = []
STRICT_ERRORS = False
SHOW_TIMINGS = False


def _read_run_only(argv: List[str]) -> None:
  global RUN_ONLY
  global STRICT_ERRORS
  global SHOW_TIMINGS
  for a in argv:
    if a.startswith('test_only='):
      RUN_ONLY = [x for x in a.split('=', 1)[1].split(',') if x]
    if a == 'strict_errors':
      STRICT_ERRORS = True
    if a == 'show_timings':
      SHOW_TIMINGS = True


def _print_header() -> None:
  print(color.Format('% 64s   %s' % ('{warning}TEST{end}', '{warning}RESULT{end}')))
  print(color.Format('% 64s   %s' % ('{warning}----{end}', '{warning}------{end}')))

@contextlib.contextmanager
def _temp_env(key: str, value: str) -> Any:
  old = os.environ.get(key)
  os.environ[key] = value
  try:
    yield
  finally:
    if old is None:
      os.environ.pop(key, None)
    else:
      os.environ[key] = old


def _import_root_from_env() -> Any:
  import_root_env = os.environ.get('LOGICAPATH')
  if not import_root_env:
    return None
  roots = import_root_env.split(':')
  if len(roots) > 1:
    return roots
  return import_root_env


def _format_parse_exception(e: BaseException) -> str:
  buf = []
  if hasattr(e, 'ShowMessage') and callable(getattr(e, 'ShowMessage')):
    try:
      import io
      s = io.StringIO()
      e.ShowMessage(stream=s)  # type: ignore[attr-defined]
      return s.getvalue()
    except Exception:  # pylint: disable=broad-exception-caught
      pass
  buf.append(f"{type(e).__name__}: {e}\n")
  return ''.join(buf)


def _parse_rules_timed(program_text: str, parser_mode: str) -> Tuple[int, str, Any, float]:
  """Returns (rc, stderr, rules_or_none, seconds)."""
  import_root = _import_root_from_env()
  t0 = time.perf_counter()
  with _temp_env('LOGICA_PARSER', parser_mode):
    try:
      rules = parse.ParseFile(program_text, import_root=import_root)['rule']
      t1 = time.perf_counter()
      return 0, '', rules, (t1 - t0)
    except parse.ParsingException as e:
      t1 = time.perf_counter()
      return 1, _format_parse_exception(e), None, (t1 - t0)
    except BaseException as e:  # noqa: BLE001
      t1 = time.perf_counter()
      return 2, traceback.format_exc() or _format_parse_exception(e), None, (t1 - t0)


def _canonical_dump(x: Any) -> str:
  # Match logica.py parse: sort_keys=True, indent=' ' (one space).
  return json.dumps(x, sort_keys=True, indent=' ') + "\n"


def _diff(a: str, b: str, from_name: str, to_name: str, limit: int = 200) -> str:
  lines = list(difflib.unified_diff(
      a.splitlines(True),
      b.splitlines(True),
      fromfile=from_name,
      tofile=to_name,
  ))
  if len(lines) <= limit:
    return ''.join(lines)
  return ''.join(lines[:limit] + [f"\n... (diff truncated to {limit} lines)\n"])


def _percentile(sorted_values: List[float], p: float) -> float:
  if not sorted_values:
    return 0.0
  if p <= 0.0:
    return sorted_values[0]
  if p >= 100.0:
    return sorted_values[-1]
  idx = (p / 100.0) * (len(sorted_values) - 1)
  lo = int(idx)
  hi = min(lo + 1, len(sorted_values) - 1)
  frac = idx - lo
  return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def _print_timing_summary(ran: List[str], ran_files: List[str], py_times: List[float], cpp_times: List[float]) -> None:
  if not ran:
    return

  py_total = sum(py_times)
  cpp_total = sum(cpp_times)
  py_sorted = sorted(py_times)
  cpp_sorted = sorted(cpp_times)

  def fmt_s(x: float) -> str:
    return f"{x:.3f}s"

  def fmt_ms(x: float) -> str:
    return f"{x * 1000.0:.1f}ms"

  print(color.Format('\n{warning}Timing summary{end} (one run per file)'))
  print(f"  Tests: {len(ran)}")
  print(
      "  Python: total %s | avg %s | p50 %s | p95 %s" % (
          fmt_s(py_total),
          fmt_ms(py_total / len(ran)),
          fmt_ms(_percentile(py_sorted, 50.0)),
          fmt_ms(_percentile(py_sorted, 95.0)),
      )
  )
  print(
      "  C++:    total %s | avg %s | p50 %s | p95 %s" % (
          fmt_s(cpp_total),
          fmt_ms(cpp_total / len(ran)),
          fmt_ms(_percentile(cpp_sorted, 50.0)),
          fmt_ms(_percentile(cpp_sorted, 95.0)),
      )
  )
  if cpp_total > 0.0:
    print(f"  Speedup (total): {py_total / cpp_total:.2f}x")

  by_py = sorted(zip(py_times, ran_files), reverse=True)[:5]
  by_cpp = sorted(zip(cpp_times, ran_files), reverse=True)[:5]
  slow_py = ', '.join([f"{fmt_ms(t)} {os.path.basename(f)}" for t, f in by_py])
  slow_cpp = ', '.join([f"{fmt_ms(t)} {os.path.basename(f)}" for t, f in by_cpp])
  print(f"  Slowest Python: {slow_py}")
  print(f"  Slowest C++:    {slow_cpp}")


def _compare_one(test_name: str, path: str) -> Tuple[bool, float, float]:
  if RUN_ONLY and test_name not in RUN_ONLY:
    return True, 0.0, 0.0

  test_result = '{warning}RUNNING{end}'
  print(color.Format('% 50s   %s' % (test_name, test_result)))

  program_text = open(path, 'r', encoding='utf-8').read()

  # Force both modes regardless of caller environment.
  py_rc, py_err, py_json, py_s = _parse_rules_timed(program_text, 'PY')
  cpp_rc, cpp_err, cpp_json, cpp_s = _parse_rules_timed(program_text, 'CPP')

  ok = True
  details = ''

  if py_rc == 0 and cpp_rc == 0:
    if py_json != cpp_json:
      ok = False
      a = _canonical_dump(py_json)
      b = _canonical_dump(cpp_json)
      details += _diff(a, b, f"python:{path}", f"cpp:{path}")
  elif py_rc != 0 and cpp_rc != 0:
    # Default: only require both to fail. Use strict_errors to compare outputs.
    if STRICT_ERRORS and py_err != cpp_err:
      ok = False
      details += "Both parsers failed, but error output differs.\n"
      details += _diff(py_err, cpp_err, f"python-stderr:{path}", f"cpp-stderr:{path}")
  else:
    ok = False
    if py_rc != 0:
      details += f"Python parser failed (rc={py_rc})\n{py_err}\n"
    if cpp_rc != 0:
      details += f"C++ parser failed (rc={cpp_rc})\n{cpp_err}\n"

  if ok:
    test_result = '{ok}PASSED{end}'
  else:
    test_result = '{error}FAILED{end}'

  line = '% 50s   %s' % (test_name, test_result)
  if SHOW_TIMINGS:
    line += '   (py=%6.1fms, cpp=%6.1fms)' % (py_s * 1000.0, cpp_s * 1000.0)
  print('\033[F\033[K' + color.Format(line))

  if not ok:
    # Keep failure output readable and similar to other test runners.
    print(details.rstrip() + "\n")

  return ok, py_s, cpp_s


def main(argv: List[str]) -> int:
  _read_run_only(argv)
  _print_header()

  files = sorted(glob.glob('integration_tests/*.l'))
  if not files:
    print('No integration_tests/*.l files found.', file=sys.stderr)
    return 2

  failed: List[str] = []
  ran: List[str] = []
  ran_files: List[str] = []
  py_times: List[float] = []
  cpp_times: List[float] = []

  for path in files:
    test_name = os.path.splitext(os.path.basename(path))[0]
    if RUN_ONLY and test_name not in RUN_ONLY:
      continue
    ran.append(test_name)
    ran_files.append(path)
    ok, py_s, cpp_s = _compare_one(test_name, path)
    py_times.append(py_s)
    cpp_times.append(cpp_s)
    if not ok:
      failed.append(test_name)

  if failed:
    _print_timing_summary(ran, ran_files, py_times, cpp_times)
    print(color.Format('{error}FAILED{end}: %d tests' % len(failed)))
    print('Failed:', ', '.join(failed))
    return 1

  _print_timing_summary(ran, ran_files, py_times, cpp_times)
  print(color.Format('{ok}PASSED{end}: %d tests' % len(ran)))
  return 0


if __name__ == '__main__':
  raise SystemExit(main(sys.argv[1:]))
