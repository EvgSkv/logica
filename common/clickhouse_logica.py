#!/usr/bin/python
#
# Copyright 2026 Google LLC
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

"""ClickHouse execution helpers for Logica.

This is a minimal HTTP client implementation meant for local/dev usage.
Connection parameters can be provided either via @Engine("clickhouse", ...)
settings or via environment variables.

Environment variables:
  LOGICA_CLICKHOUSE_HOST (default: 127.0.0.1)
  LOGICA_CLICKHOUSE_PORT (default: 8123)
  LOGICA_CLICKHOUSE_USER (default: default)
  LOGICA_CLICKHOUSE_PASSWORD (default: "")
  LOGICA_CLICKHOUSE_DATABASE (default: default)
"""

from __future__ import annotations

import csv
import io
import os
import re
import base64
import urllib.parse
import urllib.request
import urllib.error

if '.' not in __package__:
  from common import sqlite3_logica
  from common import color
else:
  from ..common import sqlite3_logica
  from ..common import color


FORMAT_RE = re.compile(r"\bFORMAT\b", re.IGNORECASE)


class ClickHouseQueryError(RuntimeError):
  def __init__(self, message, *, url=None, status=None, body=None, sql=None):
    super().__init__(message)
    self.url = url
    self.status = status
    self.body = body
    self.sql = sql


class ClickHouseCliError(RuntimeError):
  pass


def FormatCliError(e: ClickHouseQueryError) -> str:
  details = ''
  if getattr(e, 'status', None) is not None:
    details += f'HTTP {e.status}. '
  body = getattr(e, 'body', None)
  if body:
    details += body.strip()
    if ('Multi-statements are not allowed' in body or
        ('Syntax error' in body and '-- Interacting with table' in body)):
      details += '\nTip: use `logica.py ... run_in_terminal ...` (Concertina) for @Ground/multi-step programs.'
  else:
    details += str(e)
  return color.Format('[ {error}Error{end} ] ClickHouse query failed: {msg}',
                      {'msg': details})


def FormatQueryError(e: ClickHouseQueryError) -> str:
  return FormatCliError(e)


def RunQueryCli(sql, *, output_format='pretty', engine_settings=None) -> bytes:
  """Run a query for the Logica CLI.

  Returns bytes ready to be printed.
  Raises ClickHouseCliError with a color-formatted message on failure.
  """
  try:
    return RunQuery(sql, output_format=output_format,
                    engine_settings=engine_settings).encode()
  except ClickHouseQueryError as e:
    raise ClickHouseCliError(FormatCliError(e))


def Coalesce(first, second):
  return first if first is not None else second


def GetConnectionSettings(engine_settings=None):
  engine_settings = engine_settings or {}
  host = Coalesce(engine_settings.get('host'), os.environ.get('LOGICA_CLICKHOUSE_HOST')) or '127.0.0.1'
  port = int(Coalesce(engine_settings.get('port'), os.environ.get('LOGICA_CLICKHOUSE_PORT')) or 8123)
  user = Coalesce(engine_settings.get('user'), os.environ.get('LOGICA_CLICKHOUSE_USER')) or 'default'
  password = Coalesce(engine_settings.get('password'), os.environ.get('LOGICA_CLICKHOUSE_PASSWORD'))
  if password is None:
    # Default ClickHouse setups typically have an empty password for user
    # 'default'. Users can override via @Engine(..., password: ...) or env var.
    password = ''
  database = Coalesce(engine_settings.get('database'), os.environ.get('LOGICA_CLICKHOUSE_DATABASE')) or 'default'
  query_settings = engine_settings.get('settings') or {}
  if query_settings is None:
    query_settings = {}
  if not isinstance(query_settings, dict):
    raise ValueError('ClickHouse engine_settings.settings must be a dict, got: %r' % (query_settings,))
  return {
      'host': host,
      'port': port,
      'user': user,
      'password': password,
      'database': database,
      'settings': query_settings,
  }


class Connection(object):
  def __init__(self, engine_settings=None):
    self.settings = GetConnectionSettings(engine_settings)

  def RunStatement(self, sql):
    return HttpRequest(sql, settings=self.settings)

  def RunQueryHeaderRows(self, sql):
    body = HttpQuery(sql, settings=self.settings, fmt='TabSeparatedWithNames')
    if not body.strip():
      return [], []
    reader = csv.reader(io.StringIO(body), delimiter='\t')
    try:
      header = next(reader)
    except StopIteration:
      return [], []
    rows = [row for row in reader]
    return header, rows

  def RunQuery(self, sql, output_format='pretty'):
    if output_format == 'csv':
      return HttpQuery(sql, settings=self.settings, fmt='CSVWithNames')
    if output_format == 'json':
      return HttpQuery(sql, settings=self.settings, fmt='JSONEachRow')
    (header, rows) = self.RunQueryHeaderRows(sql)
    if not header and not rows:
      return ''
    return sqlite3_logica.ArtisticTable(header, rows)


def Connect(engine_settings=None):
  return Connection(engine_settings)


def ClickHouseConnect(logic_program_or_engine_settings=None):
  """Compatibility helper mirroring sqlite3_logica.SqliteConnect().

  By default connects to localhost ClickHouse with user 'default' and empty
  password (can be overridden by env vars or @Engine("clickhouse", ...) settings).
  """
  engine_settings = None
  if isinstance(logic_program_or_engine_settings, dict) or logic_program_or_engine_settings is None:
    engine_settings = logic_program_or_engine_settings
  else:
    # Treat as LogicaProgram-like object.
    try:
      annotations = logic_program_or_engine_settings.annotations.annotations
      engine_settings = annotations.get('@Engine', {}).get('clickhouse')
    except Exception:
      engine_settings = None
  return Connection(engine_settings)


def HttpRequest(sql, *, settings):
  # Use POST to avoid URL length limits (compiled SQL can be large).
  params = {'database': settings['database']}
  for k, v in (settings.get('settings') or {}).items():
    if v is None:
      continue
    params[str(k)] = str(v)
  url = f"http://{settings['host']}:{settings['port']}/?" + urllib.parse.urlencode(params)
  req = urllib.request.Request(
      url,
      data=(sql + "\n").encode('utf-8'),
      method='POST')

  # Preemptive basic auth avoids extra 401 roundtrip.
  token = base64.b64encode(
      f"{settings['user']}:{settings['password']}".encode('utf-8')).decode('ascii')
  req.add_header('Authorization', f'Basic {token}')
  req.add_header('Content-Type', 'text/plain; charset=utf-8')

  try:
    with urllib.request.urlopen(req, timeout=30) as resp:
      return resp.read().decode('utf-8', errors='replace')
  except urllib.error.HTTPError as e:
    # ClickHouse sometimes returns query errors with HTTP status codes like
    # 404 and a useful plain-text body. Surface that body to the user.
    try:
      body = e.read().decode('utf-8', errors='replace')
    except Exception:
      body = None
    raise ClickHouseQueryError(
        'ClickHouse HTTP error',
        url=getattr(e, 'filename', None),
        status=getattr(e, 'code', None),
        body=body,
        sql=sql,
    )
  except urllib.error.URLError as e:
    raise ClickHouseQueryError(
        f'ClickHouse connection error: {e}',
        url=url,
        sql=sql,
    )


def HttpQuery(sql, *, settings, fmt=None):
  # Append a FORMAT clause only when requested (DDL doesn't accept FORMAT).
  if fmt and not FORMAT_RE.search(sql):
    sql = sql.rstrip().rstrip(';') + f' FORMAT {fmt}'
  return HttpRequest(sql, settings=settings)


def RunStatement(sql, *, engine_settings=None):
  """Execute a statement and return the raw response body."""
  settings = GetConnectionSettings(engine_settings)
  return HttpRequest(sql, settings=settings)


def RunQueryHeaderRows(sql, *, engine_settings=None):
  """Run a query and return (header, rows) for Concertina runners."""
  settings = GetConnectionSettings(engine_settings)
  body = HttpQuery(sql, settings=settings, fmt='TabSeparatedWithNames')
  if not body.strip():
    return [], []

  reader = csv.reader(io.StringIO(body), delimiter='\t')
  try:
    header = next(reader)
  except StopIteration:
    return [], []
  rows = [row for row in reader]
  return header, rows


def RunQuery(sql, output_format='pretty', engine_settings=None):
  """Run a query on ClickHouse and return formatted output as a string."""
  settings = GetConnectionSettings(engine_settings)

  if output_format == 'csv':
    return HttpQuery(sql, settings=settings, fmt='CSVWithNames')

  if output_format == 'json':
    return HttpQuery(sql, settings=settings, fmt='JSONEachRow')

  # pretty / artistictable
  (header, rows) = RunQueryHeaderRows(sql, engine_settings=engine_settings)
  if not header and not rows:
    return ''
  return sqlite3_logica.ArtisticTable(header, rows)
