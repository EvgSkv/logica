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

def GetRenamingFunctor(member, root):
  """Renaming recursive cover member.

  Example.
  # Original:
  A(x) :- B(x);
  B(x) :- C(x);
  C(x) :- D(x);
  D(x) :- A(x);
  D(0);

  # After first renaming.
  D_recursive_head(x) :- A_recursive(x);
  D_recursive_head(0);

  C_recursive_head(x) :- D_recursive_head(x);

  B_recursive_head(x) :- C_recursive_head(x);

  A_recursive_head(x) :- B_recursive_head(x);

  A := A_r10();
  D := D_recursive_head(A_recursive: A);  # <-- renaming functor.
  C := C_recursive_head(A_recursive: A);
  B := B_recursive_head(A_recursive: A);
  """
  return '{0} := {0}_recursive_head({1}_recursive: {1});'.format(member, root)