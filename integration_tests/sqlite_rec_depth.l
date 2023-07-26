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

# Example of 'slow' and 'fast' recursion.

@Engine("sqlite");

# Num and SlowNum compute natural numbers.
# Size of Num grows exponentially, while SlowNum grows linearly
# with the number of recursive steps.
Num(1) distinct;
Num(2 * x + d) distinct :- Num(x), (d == 0 | d == 1);

NumSlow(1) distinct;
NumSlow(x + 1) distinct :- NumSlow(x);

Stats(num_slow_max:,
      num_slow_count:,
      num_max:,
      num_count:) :-
  num_slow_max Max= (t :- NumSlow(t)),
  num_slow_count += (1 :- NumSlow()),
  num_max Max= (t :- Num(t)),
  num_count += (1 :- Num());

Test := Stats();

