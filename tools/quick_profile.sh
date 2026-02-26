#!/usr/bin/env bash

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

set -euo pipefail

# Profiles Logica CLI *inside main()* (imports are warmed up outside profiling).
#
# Usage:
#   bash tools/quick_profile.sh <file> <command> [predicate] [flags...]
#
# Examples:
#   bash tools/quick_profile.sh integration_tests/psql_purchase_test.l print Test
#   LOGICA_PARSER=PY bash tools/quick_profile.sh integration_tests/rec_cycle_test.l print Test
#   TOP=80 bash tools/quick_profile.sh integration_tests/psql_purchase_test.l print Test
#
# Notes:
# - Suppresses stdout during profiling (so huge SQL doesn't flood the terminal).
# - Prints top functions sorted by cumulative time (cumtime).

TOP="${TOP:-40}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

python3 - "$@" <<'PY'
import cProfile
import io
import os
import pstats
import runpy
import sys

TOP = int(os.environ.get('TOP', '40'))
SHOW_STDOUT = os.environ.get('SHOW_STDOUT', '').strip().lower() in ('1', 'true', 'yes', 'y')
STDOUT_TO = os.environ.get('STDOUT_TO', '').strip() or None
args = sys.argv[1:]

if not args or args[0] in ('-h', '--help', 'help'):
	sys.stderr.write(
		'Usage: bash tools/quick_profile.sh <file> <command> [predicate] [flags...]\n'
		'Example: bash tools/quick_profile.sh integration_tests/psql_purchase_test.l print Test\n'
		'Env: LOGICA_PARSER=CPP|PY, TOP=<N>\n'
	)
	raise SystemExit(2)

# Warm-up: execute logica.py as __main__ with argv=help.
# This loads modules and defines main() outside the profiled region.
old_exit = sys.exit
old_stdout = sys.stdout
sys.exit = lambda code=0: None
sys.stdout = io.StringIO()
try:
	sys.argv = ['logica.py', 'help']
	g = runpy.run_path('logica.py', run_name='__main__')
finally:
	sys.exit = old_exit
	sys.stdout = old_stdout

main = g.get('main')
if not callable(main):
	sys.stderr.write('ERROR: Could not find main() after loading logica.py\n')
	raise SystemExit(1)

prof = cProfile.Profile()

# Optionally suppress huge stdout (SQL) during profiling.
old_stdout = sys.stdout
captured_stdout = None
if (not SHOW_STDOUT) or STDOUT_TO:
	captured_stdout = io.StringIO()
	sys.stdout = captured_stdout

rc = None
exc = None

try:
	prof.enable()
	try:
		rc = main(['logica.py'] + args)
	except SystemExit as e:
		# logica.py may sys.exit(1) on parse errors.
		rc = e.code
	except BaseException as e:  # noqa: BLE001
		exc = e
	finally:
		prof.disable()
finally:
	sys.stdout = old_stdout

if STDOUT_TO and captured_stdout is not None:
	try:
		with open(STDOUT_TO, 'w', encoding='utf-8') as f:
			f.write(captured_stdout.getvalue())
	except Exception as e:  # noqa: BLE001
		sys.stderr.write(f'WARNING: failed to write STDOUT_TO={STDOUT_TO}: {e}\n')

if exc is not None:
	sys.stderr.write(f'ERROR: {type(exc).__name__}: {exc}\n')

print('LOGICA_PARSER =', os.environ.get('LOGICA_PARSER', ''))
print('TOP =', TOP)
print('SHOW_STDOUT =', SHOW_STDOUT)
print('STDOUT_TO =', STDOUT_TO or '')
print('argv =', ' '.join(args))
print('rc =', rc)
print('\n--- top functions by cumtime ---')
pstats.Stats(prof).strip_dirs().sort_stats('cumtime').print_stats(TOP)

if exc is not None:
	raise SystemExit(1)
PY
