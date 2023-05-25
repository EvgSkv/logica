#
# Copyright 2023 Google LLC
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

# Tests for 'is' and 'is not' operators.

@Engine("sqlite");

Test(l, l_is, l_is_not, l_non_null) :-
  l = [1, 2, 3, null, 4, null, 5, 6],
  l_is Array= (i -> (l[i] is null) :- i in Range(Size(l))),
  l_is_not Array= (i -> (l[i] is not null) :- i in Range(Size(l))),
  l_non_null List= (x :- x in l, x is not null);