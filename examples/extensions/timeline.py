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
  "aggregations": [
      "PulseAdd",
      "TimelineUnionAgg = TimelineUnionFinalize * PulseConcat * TimelineToPulse",
      "TimelineIntersectAgg"],
  "functions": ["PulseMult", "PulseSum", "Threshold",
                "TimelineUnion", "TimelineIntersect", "TimelineRender"]
}

class KeyValue:
  arg: float
  value: float

# --- Internal helpers (not exported, go to C++ preamble) ---

def MergePulses(a: list[KeyValue], b: list[KeyValue]) -> list[KeyValue]:
  sa = sorted(a, key=lambda x: x.arg)
  sb = sorted(b, key=lambda x: x.arg)
  result: list[KeyValue] = []
  i = 0
  j = 0
  while i < len(sa) or j < len(sb):
    if i == len(sa):
      result.append(sb[j])
      j = j + 1
    elif j == len(sb):
      result.append(sa[i])
      i = i + 1
    elif sb[j].arg < sa[i].arg:
      result.append(sb[j])
      j = j + 1
    elif sa[i].arg < sb[j].arg:
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

def TimelineToPulse(a: list[KeyValue]) -> list[KeyValue]:
  result: list[KeyValue] = []
  i: int = 0
  while i < len(a):
    s = KeyValue()
    s.arg = a[i].arg
    s.value = 1.0
    result.append(s)
    e = KeyValue()
    e.arg = a[i].value
    e.value = -1.0
    result.append(e)
    i = i + 1
  return result

def PulseToTimeline(a: list[KeyValue]) -> list[KeyValue]:
  result: list[KeyValue] = []
  i: int = 0
  while i + 1 < len(a):
    interval = KeyValue()
    interval.arg = a[i].arg
    interval.value = a[i + 1].arg
    result.append(interval)
    i = i + 2
  return result

# --- Pulse operations (exported) ---

def PulseAdd(a: list[KeyValue], b: list[KeyValue]) -> list[KeyValue]:
  return MergePulses(a, b)

def PulseMult(a: list[KeyValue], s: float) -> list[KeyValue]:
  result: list[KeyValue] = []
  i: int = 0
  while i < len(a):
    e = KeyValue()
    e.arg = a[i].arg
    e.value = a[i].value * s
    result.append(e)
    i = i + 1
  return result

def PulseSum(a: list[KeyValue]) -> list[KeyValue]:
  sa = sorted(a, key=lambda x: x.arg)
  result: list[KeyValue] = []
  cumsum: float = 0.0
  i: int = 0
  while i < len(sa):
    cumsum = cumsum + sa[i].value
    e = KeyValue()
    e.arg = sa[i].arg
    e.value = cumsum
    result.append(e)
    i = i + 1
  return result

def Threshold(a: list[KeyValue], threshold: float) -> list[KeyValue]:
  sa = sorted(a, key=lambda x: x.arg)
  result: list[KeyValue] = []
  cumsum: float = 0.0
  above: int = 0
  i: int = 0
  while i < len(sa):
    was_above: int = above
    cumsum = cumsum + sa[i].value
    if cumsum >= threshold:
      above = 1
    else:
      above = 0
    if above == 1 and was_above == 0:
      e = KeyValue()
      e.arg = sa[i].arg
      e.value = 1.0
      result.append(e)
    elif above == 0 and was_above == 1:
      e = KeyValue()
      e.arg = sa[i].arg
      e.value = -1.0
      result.append(e)
    i = i + 1
  return result

# --- Timeline operations (exported) ---

def TimelineUnion(a: list[KeyValue], b: list[KeyValue]) -> list[KeyValue]:
  pa: list[KeyValue] = TimelineToPulse(a)
  pb: list[KeyValue] = TimelineToPulse(b)
  merged: list[KeyValue] = MergePulses(pa, pb)
  thresholded: list[KeyValue] = Threshold(merged, 1.0)
  return PulseToTimeline(thresholded)

def TimelineIntersect(a: list[KeyValue], b: list[KeyValue]) -> list[KeyValue]:
  pa: list[KeyValue] = TimelineToPulse(a)
  pb: list[KeyValue] = TimelineToPulse(b)
  merged: list[KeyValue] = MergePulses(pa, pb)
  thresholded: list[KeyValue] = Threshold(merged, 2.0)
  return PulseToTimeline(thresholded)

def PulseConcat(a: list[KeyValue], b: list[KeyValue]) -> list[KeyValue]:
  result: list[KeyValue] = []
  i: int = 0
  while i < len(a):
    result.append(a[i])
    i = i + 1
  i = 0
  while i < len(b):
    result.append(b[i])
    i = i + 1
  return result

def CollapsePulses(a: list[KeyValue]) -> list[KeyValue]:
  sa = sorted(a, key=lambda x: x.arg)
  result: list[KeyValue] = []
  i: int = 0
  while i < len(sa):
    if len(result) > 0 and result[len(result) - 1].arg == sa[i].arg:
      result[len(result) - 1].value = result[len(result) - 1].value + sa[i].value
    else:
      e = KeyValue()
      e.arg = sa[i].arg
      e.value = sa[i].value
      result.append(e)
    i = i + 1
  return result

def TimelineUnionFinalize(a: list[KeyValue]) -> list[KeyValue]:
  collapsed: list[KeyValue] = CollapsePulses(a)
  thresholded: list[KeyValue] = Threshold(collapsed, 1.0)
  return PulseToTimeline(thresholded)

def TimelineIntersectAgg(a: list[KeyValue], b: list[KeyValue]) -> list[KeyValue]:
  pa: list[KeyValue] = TimelineToPulse(a)
  pb: list[KeyValue] = TimelineToPulse(b)
  merged: list[KeyValue] = MergePulses(pa, pb)
  thresholded: list[KeyValue] = Threshold(merged, 2.0)
  return PulseToTimeline(thresholded)

def TimelineRender(a: list[KeyValue]) -> str:
  result: str = ""
  i: int = 0
  while i < len(a):
    if i > 0:
      result = result + ", "
    result = result + str(a[i].arg) + "->" + str(a[i].value)
    i = i + 1
  return result
