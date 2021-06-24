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

# Finding an arithmetic expression over ticket digits that results in 100.
# Digits should be used in the original order.
# No sign between digits mean then constitute a number.
# For instance ticket 148439 has a solution 148 - 4 * (3 + 9) = 100.
# Example usage:
#   logica ticket.l run Solution --ticket=148439  

@Engine("sqlite");
@AttachDatabase("logica_test", ":memory:");

@DefineFlag("ticket", "012345");

Ticket() = FlagValue("ticket");

Add(expr1, expr2) = "(" ++ expr1 ++ " + " ++ expr2 ++ ")";
Subtract(expr1, expr2) = "(" ++ expr1 ++ " - " ++ expr2 ++ ")";
Times(expr1, expr2) = "(" ++ expr1 ++ " * " ++ expr2 ++ ")";
Divide(expr1, expr2) = "(" ++ expr1 ++ " / " ++ expr2 ++ ")";  

@Recursive(Expression, 5);
@Ground(Expression);
Expression(i, k) = {expr: num, value: ToInt64(num)} :-
  num == Substr(Ticket(), i + 1, k),
  i in Range(Length(Ticket())),
  j in Range(6),
  k == j + 1,
  i + k <= 6,
  # Can't have a multi-digit number start with 0.
  ((k == 1) || (Substr(Ticket(), i + 1, 1) != "0"));

Expression(i, k + j) = result :-
  (
    result == {expr: Add(expr1, expr2), value: value1 + value2 } |
    result == {expr: Times(expr1, expr2), value: value1 * value2} |
    result == {expr: Subtract(expr1, expr2), value: value1 - value2} |
    (
      value2 != 0,
      result == {expr: Divide(expr1, expr2), value: value1 / (0.0 + value2)}
    )
  ),
  Expression(i, k) == e1,
  e1.expr == expr1, e1.value == value1,
  Expression(i + k, j) == e2,
  e2.expr == expr2, e2.value == value2;

Solution(solution: expr.expr) :-
  Expression(0, 6) == expr,
  expr.value == 100;

