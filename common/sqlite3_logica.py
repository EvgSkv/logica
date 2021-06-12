"""Provides connection to SQLite extended with UDFs needed by Logica."""

import csv
import io
import sys
import sqlite3
import heapq
import json

def DeFactoType(value):
  if isinstance(value, int) or isinstance(value, float):
    return 'number'
  else:
    return 'string'

class ArgMin:
  """ArgMin user defined aggregate function."""
  def __init__(self):
      self.result = []

  def step(self, arg, value, limit):
    if limit <= 0:
      raise Exception('ArgMin\'s limit must be positive.')
    if len(self.result) > 0:
      if DeFactoType(value) != DeFactoType(self.result[0][0]):
        raise Exception('ArgMin got incompatible values: %s vs %s' %
                        (repr(value), repr(self.result[0][0])))
    if len(self.result) < limit - 1:
      self.result.append((value, arg))
    elif len(self.result) == limit - 1:
      self.result.append((value, arg))
      heapq._heapify_max(self.result)
    elif len(self.result) == limit:
      if self.result[0][0] > value:
        heapq._heapreplace_max(self.result, (value, arg))
    else:
      print("ArgMin error:", self.result, arg, value, limit)
      raise Exception('ArgMin error')

  def finalize(self):
    return json.dumps([x[1] for x in sorted(self.result)])


class ArgMax:
  """ArgMax user defined aggregate functiom."""
  def __init__(self):
      self.result = []

  def step(self, arg, value, limit):
    if limit <= 0:
      raise Exception('ArgMax\'s limit must be positive.')
    if len(self.result) > 0:
      if DeFactoType(value) != DeFactoType(self.result[0][0]):
        raise Exception('ArgMax got incompatible values: %s vs %s' %
                        (repr(value), repr(self.result[0][0])))
    if len(self.result) < limit - 1:
      self.result.append((value, arg))
    elif len(self.result) == limit - 1:
      self.result.append((value, arg))
      heapq.heapify(self.result)
    elif len(self.result) == limit:
      if self.result[0][0] < value:
        heapq.heapreplace(self.result, (value, arg))
    else:
      print('ArgMax error:', self.result, arg, value, limit)
      raise Exception('ArgMax error')

  def finalize(self):
      return json.dumps([x[1] for x in reversed(sorted(self.result))])


def ArrayConcat(a, b):
  return json.dumps(json.loads(a) + json.loads(b))


def PrintToConsole(message):
  """User defined function printing to console."""
  print(message)
  return 1


def Join(array, separator):
  return separator.join(map(str, json.loads(array)))


def ReadFile(filename):
  try:
    with open(filename) as f:
      result = f.read()
  except:
    result = None
  return result


def WriteFile(filename, content):
  try:
    with open(filename, 'w') as w:
      w.write(content)
  except Exception as e:
    return str(e)
  return 'OK'


def ArtisticTable(header, rows):
  """ASCII art table for query output."""
  width = [0] * len(header)
  for r in [header] + rows:
    for i in range(len(r)):
      width[i] = max(width[i], len(str(r[i])))
  def Pad(s, w):
    return str(s) + ' ' * (w - len(str(s)))
  result = []
  top_line = '+-' + '-+-'.join('-' * w for w in width) + '-+'
  header_line = '| ' + ' | '.join(Pad(h, w) for h, w in zip(header, width)) + ' |'
  result = [top_line, header_line, top_line]
  for row in rows:
    result.append('| ' + ' | '.join(Pad(r, w) for r, w in zip(row, width)) + ' |')
  result.append(top_line)
  return '\n'.join(result)

def Csv(header, rows):
  """CSV query output."""
  stringio = io.StringIO()
  writer = csv.writer(stringio)
  writer.writerow(header)
  for row in rows:
    writer.writerow(row)
  return stringio.getvalue()

def SqliteConnect():
  con = sqlite3.connect(':memory:')
  con.create_aggregate('ArgMin', 3, ArgMin)
  con.create_aggregate('ArgMax', 3, ArgMax)
  con.create_function('PrintToConsole', 1, PrintToConsole)
  con.create_function('ARRAY_CONCAT', 2, ArrayConcat)
  con.create_function('JOIN_STRINGS', 2, Join)
  con.create_function('ReadFile', 1, ReadFile)
  con.create_function('WriteFile', 2, WriteFile)
  con.create_function('SQRT', 1, lambda x: float(x) ** 0.5)
  con.create_function('POW', 2, lambda x, p: float(x) ** p)
  sqlite3.enable_callback_tracebacks(True)
  return con


def RunSqlScript(statements, output_format):
  """Runs a sequence of statements, returning result of final."""
  assert statements, 'RunSqlScript requires non-empty statements list.'
  connect = SqliteConnect()
  cursor = connect.cursor()

  for s in statements[:-1]:
    cursor.executescript(s)
  cursor.execute(statements[-1])
  rows = cursor.fetchall()
  header = [d[0] for d in cursor.description]

  connect.close()
  if output_format == 'artistictable':
    result = ArtisticTable(header, rows)
  elif output_format == 'csv': 
    result = Csv(header, rows)
  else:
    assert False, 'Bad output format: %s' % output_format
  return result


def RunSQL(sql, output_format='artistictable'):
  """Running SQL with artistictable or csv output."""
  connect = SqliteConnect()
  cursor = connect.cursor()
  cursor.execute(sql)
  rows = cursor.fetchall()
  header = [d[0] for d in cursor.description]
  connect.close()
  if output_format == 'artistictable':
    result = ArtisticTable(header, rows)
  elif output_format == 'csv':
    result = Csv(header, rows)
  else:
    assert False, 'Bad output format: %s' % output_format
  return result

if __name__ == '__main__':
  c = SqliteConnect()
  print(RunSQL(sys.argv[1]))