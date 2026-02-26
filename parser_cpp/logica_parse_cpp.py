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

  rc = lib.logica_cpp_parse_rules_json(
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
    return json.loads(out)
  except Exception as e:
    raise RuntimeError('Failed to json-parse C++ parser output: %s' % e) from e


def _LogicapathFromImportRoot(import_root) -> Optional[str]:
  if not import_root:
    return None
  if isinstance(import_root, str):
    return import_root
  if isinstance(import_root, (list, tuple)):
    return ':'.join([str(x) for x in import_root if x])
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
    return json.loads(out)
  except Exception as e:
    raise RuntimeError('Failed to json-parse C++ parser output: %s' % e) from e
