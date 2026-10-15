// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// Scalar functions of the Socrates engine, over rows of doubles.
//
// Null is NaN (NONE). Like in SQL, arithmetic and comparisons with a null
// give null, logical operators follow three-valued logic, and a
// condition holds only when it is a definite true.
//
// compiler/socratic_logica.py reads this table to know what it may
// compile: one entry per line, FN("Name", min_args, max_args, body).

#ifndef SOCRATES_FUNCTIONS_H
#define SOCRATES_FUNCTIONS_H

#include <cmath>
#include <cstring>
#include <limits>

namespace {

typedef double num;
const num NONE = std::numeric_limits<num>::quiet_NaN();

inline bool IsNone(num x) { return std::isnan(x); }
inline bool Truthy(num x) { return !std::isnan(x) && x != 0; }
inline num Bool(bool b) { return b ? 1 : 0; }

// Three-valued logic: false wins over null, true wins over null.
inline num And(num a, num b) {
  if ((!IsNone(a) && !a) || (!IsNone(b) && !b)) return 0;
  return IsNone(a) || IsNone(b) ? NONE : 1;
}
inline num Or(num a, num b) {
  if ((!IsNone(a) && a) || (!IsNone(b) && b)) return 1;
  return IsNone(a) || IsNone(b) ? NONE : 0;
}

struct Fn {
  const char* name;
  int min_args, max_args;  // max_args < 0: any number
  num (*eval)(const num* a, int n);
};

#define FN(NAME, MIN, MAX, BODY) {NAME, MIN, MAX, [](const num* a, int n) -> num { (void)n; BODY; }},
#define NN2 if (IsNone(a[0]) || IsNone(a[1])) return NONE
#define NN1 if (IsNone(a[0])) return NONE

static const Fn FUNCTIONS[] = {
  // Arithmetic.
  FN("+", 2, 2, return a[0] + a[1])
  FN("-", 1, 2, return n == 1 ? -a[0] : a[0] - a[1])
  FN("*", 2, 2, return a[0] * a[1])
  FN("/", 2, 2, return a[0] / a[1])
  FN("%", 2, 2, NN2; return a[1] ? (num)((long long)a[0] % (long long)a[1]) : NONE)
  FN("Abs", 1, 1, return std::fabs(a[0]))
  FN("Sign", 1, 1, NN1; return a[0] > 0 ? 1 : a[0] < 0 ? -1 : 0)
  FN("Floor", 1, 1, return std::floor(a[0]))
  FN("Ceil", 1, 1, return std::ceil(a[0]))
  FN("Round", 1, 2, NN1; if (n == 1) return std::round(a[0]); num p = std::pow(10, a[1]); return std::round(a[0] * p) / p)
  FN("Trunc", 1, 1, return std::trunc(a[0]))
  FN("Sqrt", 1, 1, return std::sqrt(a[0]))
  FN("Exp", 1, 1, return std::exp(a[0]))
  FN("Log", 1, 1, return std::log(a[0]))  // natural, like the SQL path
  FN("Log2", 1, 1, return std::log2(a[0]))
  FN("Log10", 1, 1, return std::log10(a[0]))
  FN("Pow", 2, 2, return std::pow(a[0], a[1]))
  FN("Power", 2, 2, return std::pow(a[0], a[1]))
  FN("Sin", 1, 1, return std::sin(a[0]))
  FN("Cos", 1, 1, return std::cos(a[0]))
  FN("Tan", 1, 1, return std::tan(a[0]))
  FN("Asin", 1, 1, return std::asin(a[0]))
  FN("Acos", 1, 1, return std::acos(a[0]))
  FN("Atan", 1, 1, return std::atan(a[0]))
  FN("Atan2", 2, 2, return std::atan2(a[0], a[1]))
  FN("ToFloat64", 1, 1, return a[0])
  FN("ToInt64", 1, 1, NN1; return (num)(long long)a[0])
  // Comparison.
  FN("<", 2, 2, NN2; return Bool(a[0] < a[1]))
  FN("<=", 2, 2, NN2; return Bool(a[0] <= a[1]))
  FN(">", 2, 2, NN2; return Bool(a[0] > a[1]))
  FN(">=", 2, 2, NN2; return Bool(a[0] >= a[1]))
  FN("==", 2, 2, NN2; return Bool(a[0] == a[1]))
  FN("!=", 2, 2, NN2; return Bool(a[0] != a[1]))
  // Logic.
  FN("&&", 2, 2, return And(a[0], a[1]))
  FN("||", 2, 2, return Or(a[0], a[1]))
  FN("!", 1, 1, NN1; return Bool(!a[0]))
  // Null handling and choice.
  FN("IsNull", 1, 1, return Bool(IsNone(a[0])))
  FN("Coalesce", 1, -1, for (int i = 0; i < n; i++) if (!IsNone(a[i])) return a[i]; return NONE)
  FN("If", 3, 3, return Truthy(a[0]) ? a[1] : a[2])  // x -> y else z
  FN("Least", 1, -1, num r = a[0]; for (int i = 1; i < n; i++) { if (IsNone(a[i]) || IsNone(r)) return NONE; if (a[i] < r) r = a[i]; } return r)
  FN("Greatest", 1, -1, num r = a[0]; for (int i = 1; i < n; i++) { if (IsNone(a[i]) || IsNone(r)) return NONE; if (a[i] > r) r = a[i]; } return r)
};

#undef FN
#undef NN1
#undef NN2

inline const Fn* FindFunction(const char* name) {
  for (const Fn& f : FUNCTIONS) if (!strcmp(f.name, name)) return &f;
  return nullptr;
}

}  // namespace

#endif  // SOCRATES_FUNCTIONS_H
