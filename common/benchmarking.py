# Simple benchmarking utility.

from IPython.core.magic import register_cell_magic
from IPython import get_ipython
import time
from logica.common import sqlite3_logica
import pandas

timing = {}
reports = []


def Clear():
  timing = {}
  reports = []


@register_cell_magic
def loop(line, cell):
  global timing
  local_timing = {}
  ip = get_ipython()
  # Evaluate the line to get the list (e.g., "my_files")
  problem_name, iterator = ip.ev(line) 
  
  for item in iterator:
    # Inject 'item' into global namespace so the inner magic sees it
    ip.user_ns['loop_parameter'] = item 
    # Run the content as a new cell execution
    start_time = time.perf_counter()
    ip.run_cell(cell.replace('{loop_parameter}', item))
    end_time = time.perf_counter()
    elapsed = end_time - start_time
    timing[item] = elapsed
    local_timing[item] = elapsed
  report = (' === Timing for %s ===\n' % problem_name) + (
    sqlite3_logica.DataframeAsArtisticTable(
        pandas.DataFrame({'problem': list(local_timing.keys()),
        'time': list(local_timing.values())})))
  reports.append(report)
  print(report)

