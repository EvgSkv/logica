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

"""Native (in-process) bridge to the C++ Logica parser.

This module loads/builds `liblogica_parse_cpp.so` and calls the exported C ABI
functions from `parser_cpp/logica_parse.cpp` via ctypes.

When `LOGICA_PARSER=CPP`, `parser_py.parse.ParseFile` will delegate here.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import ctypes
import hashlib
import json
import os
import subprocess
import tempfile
from typing import Optional, Tuple


_PARSE_MOD = None


_LIB: Optional[ctypes.CDLL] = None

# NOTE: This bridge always prefers the pooled-heritage C++ ABI when present.
# The previous env toggles were removed to prevent accidental benchmarking or
# correctness testing of the wrong mode.


def _WrapHeritageAwareStrings(node, heritage_root=None, _match_state=None):
  """Rehydrates heritage-aware strings for parity with the Python parser.

  The Python parser uses `parser_py.parse.HeritageAwareString` for fields like
  `expression_heritage` (and `full_text`) so error reporting/type inference can
  call `.Display()` and highlight the relevant span within the *full* statement.

  The C++ parser serializes these fields as plain JSON strings. We can't always
  reconstruct exact spans (ambiguity, whitespace normalization, repeated
  substrings), but we can do a best-effort rehydration:

  - Always wrap `full_text` into `HeritageAwareString`.
  - Wrap `expression_heritage` into `HeritageAwareString`.
  - If a surrounding `full_text` exists, try to locate `expression_heritage`
    within it and set `.start/.stop/.heritage` accordingly.

  This keeps downstream code working and typically restores meaningful context
  in `.Display()`.
  """
  if _match_state is None:
    # Tracks matching progress for repeated substrings within the same
    # `full_text` heritage. Keyed by (root_id, substring).
    _match_state = {}

  if isinstance(node, list):
    return [_WrapHeritageAwareStrings(x, heritage_root, _match_state) for x in node]

  if isinstance(node, dict):
    parse_mod = _GetParseModule()
    HeritageAwareString = getattr(parse_mod, 'HeritageAwareString', str)

    def _needs_alignment(x) -> bool:
      if not isinstance(x, HeritageAwareString):
        return True
      try:
        text = str(x)
        return (
            getattr(x, 'heritage', text) == text and
            getattr(x, 'start', 0) == 0 and
            getattr(x, 'stop', len(text)) == len(text)
        )
      except Exception:  # pylint: disable=broad-exception-caught
        return True

    local_root = heritage_root
    if 'full_text' in node and isinstance(node.get('full_text'), str):
      full_text_value = node.get('full_text')
      if not isinstance(full_text_value, HeritageAwareString):
        full_text_value = HeritageAwareString(full_text_value)
      local_root = full_text_value

    result = {}
    for key, value in node.items():
      if key == 'full_text' and local_root is not None:
        result[key] = local_root
        continue

      if key == 'expression_heritage' and isinstance(value, str):
        # If expression_heritage is exactly the same text as the surrounding
        # full_text, reuse the same HeritageAwareString instance. This avoids
        # retaining multiple copies of large rule texts that JSON decoding would
        # otherwise duplicate.
        if local_root is not None and str(value) == str(local_root):
          result[key] = local_root
          continue

        expr_value = value
        if not isinstance(expr_value, HeritageAwareString):
          expr_value = HeritageAwareString(expr_value)

        if local_root is not None and _needs_alignment(expr_value):
          heritage_text = getattr(local_root, 'heritage', str(local_root))
          substring = str(expr_value)
          root_id = id(local_root)
          start_from = _match_state.get((root_id, substring), 0)
          idx = str(heritage_text).find(substring, start_from)
          if idx == -1 and start_from:
            # Fallback if traversal order doesn't align with textual order.
            idx = str(heritage_text).find(substring)
          if idx != -1:
            expr_value.heritage = heritage_text
            expr_value.start = idx
            expr_value.stop = idx + len(substring)
            _match_state[(root_id, substring)] = idx + len(substring)

        result[key] = expr_value
        continue

      result[key] = _WrapHeritageAwareStrings(value, local_root, _match_state)
    return result

  return node


def _DecodePooledHeritageOutput(node):
  """Decodes pooled-heritage JSON output from the C++ parser.

  When available, the C++ shared library can emit a wrapper JSON object:
    {"__string_table": [...], "tree": ...}

  In the tree, spans are represented as:
    ["__hs", <idx>, <start_byte>, <stop_byte>]

  (Legacy format is also accepted for forward/backward compatibility:
    {"__hs": <idx>, "start": <start_byte>, "stop": <stop_byte>})

  This function reconstructs `parser_py.parse.HeritageAwareString` objects so
  downstream code sees the same types as the Python parser.
  """
  if not (isinstance(node, dict) and '__string_table' in node and 'tree' in node):
    return node

  string_table = node.get('__string_table')
  tree = node.get('tree')
  if not isinstance(string_table, list):
    return tree

  parse_mod = _GetParseModule()
  HeritageAwareString = getattr(parse_mod, 'HeritageAwareString', str)

  table_len = len(string_table)

  # Cache: idx -> bool (isascii). Built lazily.
  ascii_flags = [None] * table_len

  # Cache: idx -> (utf8_byte_len, byte_offset->char_offset mapping)
  # Built lazily only for non-ascii strings.
  byte_to_char_map = [None] * table_len

  # Cache: (idx, start_off, stop_off) -> HeritageAwareString
  span_cache = {}

  def is_ascii(idx: int, heritage: str) -> bool:
    v = ascii_flags[idx]
    if v is None:
      v = heritage.isascii()
      ascii_flags[idx] = v
    return bool(v)

  def get_map(idx: int, heritage: str):
    cached = byte_to_char_map[idx]
    if cached is not None:
      return cached
    b = heritage.encode('utf-8')
    mapping = [0] * (len(b) + 1)
    chars = 0
    for i, byt in enumerate(b):
      # UTF-8 continuation bytes are 10xxxxxx.
      if (byt & 0xC0) != 0x80:
        chars += 1
      mapping[i + 1] = chars
    cached = (len(b), mapping)
    byte_to_char_map[idx] = cached
    return cached

  def decode_span(idx: int, start_b: int, stop_b: int):
    if idx < 0 or idx >= table_len:
      return None
    heritage = string_table[idx]
    if not isinstance(heritage, str):
      return None
    if start_b < 0:
      start_b = 0
    if stop_b < start_b:
      stop_b = start_b

    cache_key = (idx, start_b, stop_b)
    cached = span_cache.get(cache_key)
    if cached is not None:
      return cached

    if is_ascii(idx, heritage):
      start_c = min(start_b, len(heritage))
      stop_c = min(stop_b, len(heritage))
    else:
      blen, mapping = get_map(idx, heritage)
      if start_b > blen:
        start_b = blen
      if stop_b > blen:
        stop_b = blen
      start_c = mapping[start_b]
      stop_c = mapping[stop_b]

    text = heritage[start_c:stop_c]
    hs = HeritageAwareString(text)
    try:
      hs.heritage = heritage
      hs.start = start_c
      hs.stop = stop_c
    except Exception:  # pylint: disable=broad-exception-caught
      pass
    span_cache[cache_key] = hs
    return hs

  def decode_known_key_span(value):
    # New compact encoding: [idx, start_b, stop_b].
    if isinstance(value, list) and len(value) == 3:
      idx, start_b, stop_b = value
      if isinstance(idx, int) and isinstance(start_b, int) and isinstance(stop_b, int):
        hs = decode_span(idx, start_b, stop_b)
        if hs is not None:
          return hs
    # Legacy v1 encoding: ["__hs", idx, start_b, stop_b].
    if isinstance(value, list) and len(value) == 4 and value and value[0] == '__hs':
      idx = value[1]
      start_b = value[2]
      stop_b = value[3]
      if isinstance(idx, int) and isinstance(start_b, int) and isinstance(stop_b, int):
        hs = decode_span(idx, start_b, stop_b)
        if hs is not None:
          return hs
    # Legacy dict encoding: {"__hs": idx, "start": b, "stop": b}
    if isinstance(value, dict) and len(value) == 3 and '__hs' in value and 'start' in value and 'stop' in value:
      idx = value.get('__hs')
      start_b = value.get('start')
      stop_b = value.get('stop')
      if isinstance(idx, int) and isinstance(start_b, int) and isinstance(stop_b, int):
        hs = decode_span(idx, start_b, stop_b)
        if hs is not None:
          return hs
    return value

  def decode(x):
    # Mutate containers in-place to avoid allocating a fresh list/dict for every
    # node; the JSON tree returned by json.loads is not shared.
    if isinstance(x, list):
      for i, v in enumerate(x):
        if isinstance(v, (list, dict)):
          x[i] = decode(v)
      return x

    if isinstance(x, dict):
      # Decode spans only under known keys to avoid misinterpreting ordinary
      # numeric lists elsewhere in the AST.
      if 'full_text' in x:
        x['full_text'] = decode_known_key_span(x.get('full_text'))
      if 'expression_heritage' in x:
        x['expression_heritage'] = decode_known_key_span(x.get('expression_heritage'))

      for k, v in x.items():
        if k in ('full_text', 'expression_heritage'):
          continue
        if isinstance(v, (list, dict)):
          x[k] = decode(v)
      return x

    return x

  return decode(tree)


def _GetParseModule():
  global _PARSE_MOD
  if _PARSE_MOD is not None:
    return _PARSE_MOD
  # Import lazily to avoid cycles when parser_py.parse imports us.
  if '.' not in (__package__ or ''):
    from parser_py import parse as _parse  # type: ignore
  else:
    from ..parser_py import parse as _parse  # type: ignore
  _PARSE_MOD = _parse
  return _PARSE_MOD


def _CppParsingExceptionClass(exception_thrower=None):
  """Builds an exception class that prints C++ formatted errors.

  If exception_thrower is provided (e.g. parser_py.parse.ParsingException), the
  returned exception is a subclass of it so existing catches still work.
  """
  if exception_thrower is None:
    try:
      exception_thrower = _GetParseModule().ParsingException
    except Exception:  # pylint: disable=broad-exception-caught
      exception_thrower = Exception

  class _CppParsingException(exception_thrower):
    def __init__(self, formatted_error_text: str):
      Exception.__init__(self, 'C++ parser error.')
      self._formatted_error_text = formatted_error_text or ''

    def ShowMessage(self, stream=os.sys.stderr):
      text = self._formatted_error_text
      stream.write(text)
      if text and not text.endswith('\n'):
        stream.write('\n')

  return _CppParsingException


def GetParserMode() -> str:
  """Returns the requested parser mode.

  Controlled by the `LOGICA_PARSER` environment variable.

  - Unset/empty => 'PY'
  - 'PY' or 'CPP' (case-insensitive) are accepted.
  - Any other value raises ValueError.
  """
  raw = os.environ.get('LOGICA_PARSER', '')
  mode = (raw or '').strip().upper()
  if not mode:
    return 'PY'
  if mode in ('PY', 'CPP'):
    return mode
  raise ValueError(
      'Unsupported LOGICA_PARSER=%r. Expected PY or CPP.' % raw
  )


def UseCppParser() -> bool:
  return GetParserMode() == 'CPP'


def _RepoRoot() -> str:
  # This file lives in <repo>/parser_cpp/, so repo root is one level up.
  return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _CppParserCacheRoot() -> str:
  """Returns a writable cache root for build artifacts."""
  xdg_cache = os.environ.get('XDG_CACHE_HOME')
  if xdg_cache:
    return os.path.join(os.path.abspath(os.path.expanduser(xdg_cache)), 'logica')

  home = os.path.expanduser('~')
  if home and home != '~':
    return os.path.join(home, '.cache', 'logica')

  return os.path.join(tempfile.gettempdir(), 'logica_cache')


def _CppParserCacheDir(repo_root: Optional[str] = None) -> str:
  root = os.path.realpath(repo_root or _RepoRoot())
  digest = hashlib.sha256(root.encode('utf-8')).hexdigest()[:12]
  return os.path.join(_CppParserCacheRoot(), 'cpp_parser', digest)


def CppParserPaths(repo_root: Optional[str] = None) -> Tuple[str, str]:
  root = repo_root or _RepoRoot()
  cache_dir = _CppParserCacheDir(root)
  so_path = os.path.join(cache_dir, 'liblogica_parse_cpp.so')
  src_path = os.path.join(root, 'parser_cpp', 'logica_parse.cpp')
  return so_path, src_path


def EnsureCppParserSharedObject(repo_root: Optional[str] = None) -> str:
  so_path, src_path = CppParserPaths(repo_root)
  if not os.path.isfile(src_path):
    raise RuntimeError('C++ parser source not found: %s' % src_path)

  try:
    os.makedirs(os.path.dirname(so_path), exist_ok=True)
  except OSError:
    # Best-effort fallback: if the cache root is not writable.
    fallback_dir = os.path.join(tempfile.gettempdir(), 'logica_cpp_parser')
    os.makedirs(fallback_dir, exist_ok=True)
    so_path = os.path.join(fallback_dir, os.path.basename(so_path))

  need_build = not os.path.isfile(so_path)
  if not need_build:
    try:
      need_build = os.path.getmtime(so_path) < os.path.getmtime(src_path)
    except OSError:
      need_build = True

  if not need_build:
    return so_path

  try:
    tmp_fd, tmp_so_path = tempfile.mkstemp(
        dir=os.path.dirname(so_path),
        prefix=os.path.basename(so_path) + '.tmp.',
    )
    os.close(tmp_fd)
    cmd = [
        'g++',
        '-std=c++20',
        '-O2',
        '-fPIC',
        '-shared',
        '-Wall',
        '-Wextra',
        '-pedantic',
        '-DLOGICA_PARSE_LIBRARY',
        '-o',
        tmp_so_path,
        src_path,
    ]
    subprocess.check_call(cmd)
    os.replace(tmp_so_path, so_path)
  except Exception as e:
    try:
      if 'tmp_so_path' in locals() and os.path.exists(tmp_so_path):
        os.remove(tmp_so_path)
    except OSError:
      pass
    raise RuntimeError(
        'Failed to build C++ parser shared library. '
        'Install g++ with C++20 support or build liblogica_parse_cpp.so manually.'
    ) from e

  return so_path


def LoadCppParserLib(repo_root: Optional[str] = None) -> ctypes.CDLL:
  global _LIB
  if _LIB is not None:
    return _LIB

  so_path = EnsureCppParserSharedObject(repo_root)
  lib = ctypes.CDLL(so_path)

  lib.logica_cpp_parse_rules_json.argtypes = [
      ctypes.c_char_p,  # program_text
      ctypes.c_char_p,  # file_name
      ctypes.c_char_p,  # logicapath (colon-separated)
      ctypes.c_int,     # full
      ctypes.POINTER(ctypes.c_void_p),
      ctypes.POINTER(ctypes.c_void_p),
  ]
  lib.logica_cpp_parse_rules_json.restype = ctypes.c_int

  pooled = getattr(lib, 'logica_cpp_parse_rules_json_pooled', None)
  if pooled is not None:
    pooled.argtypes = [
        ctypes.c_char_p,  # program_text
        ctypes.c_char_p,  # file_name
        ctypes.c_char_p,  # logicapath (colon-separated)
        ctypes.c_int,     # full
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    pooled.restype = ctypes.c_int

  lib.logica_cpp_free.argtypes = [ctypes.c_void_p]
  lib.logica_cpp_free.restype = None

  _LIB = lib
  return lib


def ParseRulesJsonNative(program_text: str,
                         file_name: str = 'main',
                         logicapath: Optional[str] = None,
                         full: bool = False,
                         repo_root: Optional[str] = None) -> Tuple[int, str, str]:
  lib = LoadCppParserLib(repo_root)
  out_ptr = ctypes.c_void_p()
  err_ptr = ctypes.c_void_p()

  # Pooled heritage ABI is the only supported mode for the C++ parser bridge.
  # If the symbol is missing, we likely loaded a stale/older shared library.
  fn = getattr(lib, 'logica_cpp_parse_rules_json_pooled', None)
  if fn is None:
    raise RuntimeError(
        'C++ parser shared library does not export logica_cpp_parse_rules_json_pooled. '
        'This likely means a stale/older liblogica_parse_cpp.so is being used. '
        'Try deleting the cache dir and re-running to rebuild.'
    )
  rc = fn(
      program_text.encode('utf-8'),
      file_name.encode('utf-8'),
      logicapath.encode('utf-8') if logicapath else None,
      1 if full else 0,
      ctypes.byref(out_ptr),
      ctypes.byref(err_ptr),
  )

  out = ''
  err = ''

  if out_ptr.value:
    out = ctypes.string_at(out_ptr.value).decode('utf-8', errors='replace')
    lib.logica_cpp_free(out_ptr)

  if err_ptr.value:
    err = ctypes.string_at(err_ptr.value).decode('utf-8', errors='replace')
    lib.logica_cpp_free(err_ptr)

  return int(rc), out, err


def ParseRules(program_text: str,
               file_name: str = 'main',
               logicapath: Optional[str] = None,
               repo_root: Optional[str] = None,
               exception_thrower=None):
  rc, out, err = ParseRulesJsonNative(
      program_text,
      file_name=file_name,
      logicapath=logicapath,
      full=False,
      repo_root=repo_root,
  )
  if rc != 0:
    raise _CppParsingExceptionClass(exception_thrower)(err)
  try:
    loaded = json.loads(out)
    pooled = isinstance(loaded, dict) and '__string_table' in loaded and 'tree' in loaded
    loaded = _DecodePooledHeritageOutput(loaded)
    if pooled:
      return loaded
    return _WrapHeritageAwareStrings(loaded)
  except Exception as e:
    raise RuntimeError('Failed to json-parse C++ parser output: %s' % e) from e


def _LogicapathFromImportRoot(import_root) -> Optional[str]:
  if not import_root:
    return None
  if isinstance(import_root, str):
    return import_root
  if isinstance(import_root, (list, tuple)):
    return ':'.join([str(x) for x in import_root])
  raise TypeError('Unexpected import_root type: %r' % (type(import_root),))


def ParseFile(program_text: str,
              import_root=None,
              this_file_name: str = 'main',
              repo_root: Optional[str] = None,
              exception_thrower=None,
              **_unused_kwargs):
  """C++ equivalent of parser_py.parse.ParseFile.

  Returns a dict with at least the 'rule' key.
  """
  rc, out, err = ParseRulesJsonNative(
      program_text,
      file_name=this_file_name or 'main',
      logicapath=_LogicapathFromImportRoot(import_root),
      full=True,
      repo_root=repo_root,
  )
  if rc != 0:
    raise _CppParsingExceptionClass(exception_thrower)(err)
  try:
    loaded = json.loads(out)
    pooled = isinstance(loaded, dict) and '__string_table' in loaded and 'tree' in loaded
    loaded = _DecodePooledHeritageOutput(loaded)
    if pooled:
      return loaded
    return _WrapHeritageAwareStrings(loaded)
  except Exception as e:
    raise RuntimeError('Failed to json-parse C++ parser output: %s' % e) from e
