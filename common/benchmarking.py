# Simple benchmarking utility.

from IPython.core.magic import register_cell_magic
from IPython import get_ipython
import time
from logica.common import sqlite3_logica
import pandas
import signal

timing = {}
reports = []
timeout = 200

def Clear():
  global timing, reports
  timing = {}
  reports = []


@register_cell_magic
def loop(line, cell):
  global timing
  local_timing = {}
  ip = get_ipython()
  problem_name, iterator = ip.ev(line)
  stop = False

  for item in iterator:
    if stop:
      print('Skipping %s (previous timeout).' % item)
      timing[item] = local_timing[item] = 'TIMEOUT (> %d)' % timeout
      continue

    print('Running %s.' % item)
    ip.user_ns['loop_parameter'] = item

    timed_out = [False]
    def handler(signum, frame):
      timed_out[0] = True
      raise KeyboardInterrupt("Timeout")

    old_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(timeout)

    start_time = time.perf_counter()
    try:
      ip.run_cell(cell.replace('{loop_parameter}', item))
    finally:
      signal.alarm(0)
      signal.signal(signal.SIGALRM, old_handler)
    elapsed = time.perf_counter() - start_time

    if timed_out[0]:
      print('*** TIMEOUT on %s ***' % item)
      stop = True
      elapsed = 'TIMEOUT (> %d)' % timeout

    timing[item] = elapsed
    local_timing[item] = elapsed

  report = (' === Timing for %s ===\n' % problem_name) + (
    sqlite3_logica.DataframeAsArtisticTable(
        pandas.DataFrame({'problem': list(local_timing.keys()),
        'time': list(local_timing.values())})))
  reports.append(report)
  print(report)

