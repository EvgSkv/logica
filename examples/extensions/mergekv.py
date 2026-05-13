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

LOGICA_EXTENSION = {
  "aggregations": ["MergeKV"]
}

class KeyValue:
  arg: str
  value: float

def MergeKV(a: list[KeyValue], b: list[KeyValue]) -> list[KeyValue]:
  sa = sorted(a, key=lambda x: x.arg)
  sb = sorted(b, key=lambda x: x.arg)
  result: list[KeyValue] = []
  i = 0
  j = 0
  while i < len(sa) or j < len(sb):
    if i == len(sa) or sb[j].arg < sa[i].arg:
      result.append(sb[j])
      j = j + 1
    elif j == len(sb) or sa[i].arg < sb[j].arg:
      result.append(sa[i])
      i = i + 1
    else:
      e = KeyValue()
      e.arg = sa[i].arg
      e.value = sa[i].value + sb[j].value
      result.append(e)
      i = i + 1
      j = j + 1
  return result
