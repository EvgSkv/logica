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

# Testing ArgMax, ArgMin, ArgMaxK and ArgMinK builtins.

@Engine("presto", server: "localhost:8090");

Data(v: 10, payload: "a");
Data(v: 5, payload: "b");
Data(v: 20, payload: "c");
Data(v: 100, payload: "d");
Data(v: 30, payload: "e");
Data(v: 15, payload: "f");

TestArgMax() ArgMax= payload -> v :- Data(v:, payload:);
TestArgMin() ArgMin= payload -> v :- Data(v:, payload:);

ArgMax3(x) = ArgMaxK(x, 3);
ArgMin2(x) = ArgMinK(x, 2);

A(arrow) =
  SqlExpr("CAST(ROW({arg}, {value}) AS ROW(arg VARCHAR, value BIGINT))",
  {arg: arrow.arg, value: arrow.value});

TestArgMaxK() ArgMax3= A(payload -> v) -> v :- Data(v:, payload:);
TestArgMinK() ArgMin2= A(payload -> v) -> v :- Data(v:, payload:);

ArrAsc() Array= v -> payload :- Data(v:, payload:);
ArrDesc() Array= (-v) -> payload :- Data(v:, payload:);

@OrderBy(Test, "arg_opt");
Test(opt: "Max", arg_opt: TestArgMax(), arg_opt_k: TestArgMaxK(), arr: ArrDesc());
Test(opt: "Min", arg_opt: TestArgMin(), arg_opt_k: TestArgMinK(), arr: ArrAsc());
