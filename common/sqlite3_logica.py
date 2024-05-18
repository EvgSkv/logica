"""Provides connection to SQLite extended with UDFs needed by Logica."""

import csv
import hashlib
import io
import math
import sys
import sqlite3
import heapq
import json
import re


if '.' not in __package__:
  from common import intelligence
else:
  from ..common import intelligence


def DeFactoType(value):
  if isinstance(value, int) or isinstance(value, float):
    return 'number'
  else:
    return 'string'

def LoadJson(s):
  try:
    return json.loads(s)
  except ValueError as e:
    print('Failed to parse JSON object: %s' % s, file=sys.stderr)
    raise e

class ArgMin:
  """ArgMin user defined aggregate function."""
  def __init__(self):
      self.result = []

  def step(self, arg, value, limit):
    if limit is not None and limit <= 0:
      raise Exception('ArgMin\'s limit must be positive.')
    if len(self.result) > 0:
      if DeFactoType(value) != DeFactoType(self.result[0][0]):
        raise Exception('ArgMin got incompatible values: %s vs %s' %
                        (repr(value), repr(self.result[0][0])))
    if limit is None or len(self.result) < limit - 1:
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


class TakeFirst:
  """Taking first of values seen."""
  def __init__(self):
    self.result = None

  def step(self, new_value):
    self.result = self.result or new_value
  
  def finalize(self):
    return self.result


class ArgMax:
  """ArgMax user defined aggregate function."""
  def __init__(self):
      self.result = []

  def step(self, arg, value, limit):
    if limit is not None and limit <= 0:
      raise Exception('ArgMax\'s limit must be positive.')
    if len(self.result) > 0:
      if DeFactoType(value) != DeFactoType(self.result[0][0]):
        raise Exception('ArgMax got incompatible values: %s vs %s' %
                        (repr(value), repr(self.result[0][0])))
    if limit is None or len(self.result) < limit - 1:
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


class DistinctListAgg:
  """Collecting a list of distinct elements."""
  def __init__(self):
    self.result = set()

  def step(self, element):
    self.result.add(element)
  
  def finalize(self):
    return json.dumps(list(self.result))


class ArrayConcatAgg:
  """List concatenation aggregation."""
  def __init__(self):
    self.result = []
  
  def step(self, a):
    if a is None:
      return
    self.result.extend(LoadJson(a))
  
  def finalize(self):
    return json.dumps(self.result)
  

def ArrayConcat(a, b):
  if a is None or b is None:
    return None
  if not isinstance(a, str):
    print('Bad first concatenation argument:', a, b)
  if not isinstance(b, str):
    print('Bad second concatenation argument:', a, b)
  return json.dumps(LoadJson(a) + LoadJson(b))


def PrintToConsole(message):
  """User defined function printing to console."""
  print(message)
  return 1


def Join(array, separator):
  return separator.join(map(str, LoadJson(array)))


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

def SortList(input_list_json):
  return json.dumps(list(sorted(LoadJson(input_list_json))))

def InList(item, a_list):
  return item in LoadJson(a_list)

def AssembleRecord(field_value_list):
  field_value_list = LoadJson(field_value_list)
  result = {}
  for kv in field_value_list:
    if isinstance(kv, dict) and 'arg' in kv and 'value' in kv:
      k = kv['arg']
      v = kv['value']
      result[k] = v
    else:
      return 'ERROR: AssembleRecord called on bad input: %s' % field_value_list
  return json.dumps(result)

def DisassembleRecord(record):
  record = LoadJson(record)
  return json.dumps([{'arg': k, 'value': v} for k, v in record.items()])

def UserError(error_text):
  print('[USER DEFINED ERROR]: %s' % error_text)
  assert False

def Fingerprint(s):
  return int(hashlib.md5(str(s).encode()).hexdigest()[:16], 16) - (1 << 63)

def SqliteConnect():
  con = sqlite3.connect(':memory:')
  con.create_aggregate('ArgMin', 3, ArgMin)
  con.create_aggregate('ArgMax', 3, ArgMax)
  con.create_aggregate('DistinctListAgg', 1, DistinctListAgg)
  con.create_aggregate('ARRAY_CONCAT_AGG', 1, ArrayConcatAgg)
  con.create_aggregate('ANY_VALUE', 1, TakeFirst)
  con.create_function('PrintToConsole', 1, PrintToConsole)
  con.create_function('ARRAY_CONCAT', 2, ArrayConcat)
  con.create_function('JOIN_STRINGS', 2, Join)
  con.create_function('ReadFile', 1, ReadFile)
  con.create_function('WriteFile', 2, WriteFile)
  con.create_function('SQRT', 1, lambda x: float(x) ** 0.5)
  con.create_function('POW', 2, lambda x, p: float(x) ** p)
  con.create_function('Exp', 1, lambda x: math.exp(x))
  con.create_function('Log', 1, lambda x: math.log(x))
  con.create_function('Sin', 1, lambda x: math.sin(x))
  con.create_function('Cos', 1, lambda x: math.cos(x))
  con.create_function('Asin', 1, lambda x: math.asin(x))
  con.create_function('Acos', 1, lambda x: math.acos(x))
  con.create_function('Split', 2, lambda x, y: json.dumps((x.split(y))))
  con.create_function('ARRAY_TO_STRING', 2, lambda x, y: y.join(x))
  con.create_function('SortList', 1, SortList)
  con.create_function('MagicalEntangle', 2, lambda x, y: x)
  con.create_function('IN_LIST', 2, InList)
  con.create_function('ERROR', 1, UserError)
  con.create_function('Fingerprint', 1, Fingerprint)
  con.create_function('Floor', 1, math.floor)
  con.create_function('RE_SUB', 5, lambda string, pattern, repl="", count=0, flags=0: \
                                    re.sub(pattern, repl, string ,count, flags))
  con.create_function('Intelligence', 1, intelligence.Intelligence)
  con.create_function('AssembleRecord', 1, AssembleRecord)
  con.create_function('DisassembleRecord', 1, DisassembleRecord)
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