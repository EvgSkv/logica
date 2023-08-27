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

@Engine("psql");

@Ground(T);
T(a: 1, b: "I");
T(a: 2, b: "II");
T(a: 3, b: "III");

@Ground(R);
R(f: {c: 5, d: [{e: "e"}]}, g: "g");

SaveT() += 1 :- T();
SaveR() += 1 :- R();

@Ground(D, "logica_test.T");
@Ground(RawE, "logica_test.R");

E(..r) :-
  RawE(..r),
  r ~ {f: {c: Num, d: [{e: Str}]}, g: Str};

@Ground(PrepareData);
PrepareData("done") += 1 :- SaveT() | SaveR();

Test({f:, g:}) Array= a -> {a:, b:} :-
  PrepareData(),
  D(a:, b:),
  E(f:, g:),
  a ~ Num, b ~ Str;