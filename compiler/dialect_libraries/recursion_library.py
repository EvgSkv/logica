#!/usr/bin/python
#
# Copyright 2020 Google LLC
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

def GetRecursionFunctor(depth):
  """Returns functor that unfolds recursion.

  Example:
  P_r0 := P_recursive_head(P_recursive: nil);
  P_r1 := P_recursive_head(P_recursive: P_r0);
  P_r2 := P_recursive_head(P_recursive: P_r1);
  P_r3 := P_recursive_head(P_recursive: P_r2);
  P := P_r3();
  """
  result_lines = ['P_r0 := P_recursive_head(P_recursive: nil);']
  for i in range(depth):
      result_lines.append(
          'P_r{1} := P_recursive_head(P_recursive: P_r{0});'.format(i, i + 1))
  result_lines.append('P := P_r{0}();'.format(depth))
  return '\n'.join(result_lines)
