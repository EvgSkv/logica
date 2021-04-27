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

# Example of a program running on Presto engine.

# ********
# * This only works if you have Presto installed and CLI available as
# * a command `presto`.
# *

# By default running on catalogue named 'memory'.
@Engine("presto");

# Define natural numbers from 0 to 29.
N(x) :- x in Range(30);
# Define primes.
Prime(prime: x) :-
  N(x),
  x > 1,
  ~(
    N(y),
    y > 1,
    y != x,
    Mod(x, y) == 0
  );