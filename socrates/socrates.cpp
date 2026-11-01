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

// Socrates: native evaluator of one recursive component of a Logica program.
//
// Built on first use by compiler/socratic_logica.py (like the C++ parser)
// and run as a subprocess. The component arrives as a JSON spec:
// relations (inputs read from CSV, state relations written to CSV) and
// conjunctive rules.
//
// Semantics: a change of a fact is the unit of work. Changed facts form a
// FIFO queue with generation markers; a "round" drains one generation.
// @Recursive(P, N) runs N rounds, infinity runs until the queue is empty.
//
// A rule turns a changed body fact into affected head keys (joined with
// the other atoms through indexes on the bound columns, atoms in the
// order they were written, the changed atom first). How a head absorbs
// a change depends only on its aggregates:
//   * every value column is a semilattice (Min, Max, ArgMin, ArgMax, or a
//     set): the new contribution is pushed into the current value;
//   * otherwise (+=, =, mixtures): the affected keys are recomputed from
//     all their contributions, the aggregates being black boxes.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <functional>
#include <limits>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <chrono>
#ifdef __APPLE__
#include <mach/mach.h>
#endif
#ifdef _OPENMP
#include <omp.h>
#else
static int omp_get_max_threads() { return 1; }
static int omp_get_thread_num() { return 0; }
static void omp_set_num_threads(int) {}
#endif

#include "functions.h"

namespace {

typedef int64_t i64;  // row scalar `num` (functions.h): integers are exact up to 2^53

double Now() {
  return std::chrono::duration<double>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
}

[[noreturn]] void Fail(const std::string& message) {
  fprintf(stderr, "socrates: %s\n", message.c_str());
  exit(2);
}

// ----------------------------------------------------------------------
// Minimal JSON reader.
struct Json {
  enum Kind { NUL, BOOL, NUM, STR, ARR, OBJ } kind = NUL;
  bool b = false;
  double num = 0;
  std::string str;
  std::vector<Json> arr;
  std::vector<std::pair<std::string, Json>> obj;
  const Json* Get(const std::string& k) const {
    for (auto& kv : obj) if (kv.first == k) return &kv.second;
    return nullptr;
  }
  const Json& At(const std::string& k) const {
    const Json* j = Get(k);
    if (!j) Fail("missing key " + k);
    return *j;
  }
};

struct JsonParser {
  const char* s; size_t i = 0;
  explicit JsonParser(const char* text) : s(text) {}
  void Ws() { while (s[i] == ' ' || s[i] == '\n' || s[i] == '\t' || s[i] == '\r') i++; }
  Json Parse() {
    Ws(); Json j;
    if (s[i] == '{') {
      j.kind = Json::OBJ; i++; Ws();
      while (s[i] != '}') {
        Json k = Parse(); Ws(); i++;
        Json v = Parse(); j.obj.emplace_back(k.str, std::move(v)); Ws();
        if (s[i] == ',') { i++; Ws(); }
      }
      i++;
    } else if (s[i] == '[') {
      j.kind = Json::ARR; i++; Ws();
      while (s[i] != ']') { j.arr.push_back(Parse()); Ws(); if (s[i] == ',') { i++; Ws(); } }
      i++;
    } else if (s[i] == '"') {
      j.kind = Json::STR; i++;
      while (s[i] != '"') { if (s[i] == '\\') i++; j.str += s[i++]; }
      i++;
    } else if (!strncmp(s + i, "true", 4)) { j.kind = Json::BOOL; j.b = true; i += 4; }
    else if (!strncmp(s + i, "false", 5)) { j.kind = Json::BOOL; i += 5; }
    else if (!strncmp(s + i, "null", 4)) { i += 4; }
    else { char* e; j.kind = Json::NUM; j.num = strtod(s + i, &e); i = e - s; }
    return j;
  }
};

// ----------------------------------------------------------------------
// Expressions over rule variables.
struct Expr {
  enum Kind { VAR, CONST, OP } kind = CONST;
  // The arithmetic and comparisons of the hot loops are evaluated inline;
  // everything else goes through the function table (functions.h).
  enum Fast { NONE_, ADD, SUB, MUL, DIV, LT, LE, GT, GE, EQ, NE } fast = NONE_;
  int var = -1;
  num value = 0;
  std::string op;
  const Fn* fn = nullptr;  // OP: the function
  std::vector<Expr> args;
};

Expr::Fast FastOp(const std::string& o, size_t nargs) {
  if (nargs != 2) return Expr::NONE_;
  if (o == "+") return Expr::ADD;
  if (o == "-") return Expr::SUB;
  if (o == "*") return Expr::MUL;
  if (o == "/") return Expr::DIV;
  if (o == "<") return Expr::LT;
  if (o == "<=") return Expr::LE;
  if (o == ">") return Expr::GT;
  if (o == ">=") return Expr::GE;
  if (o == "==") return Expr::EQ;
  if (o == "!=") return Expr::NE;
  return Expr::NONE_;
}

inline num FastEval(int fast, num a, num b) {
  switch (fast) {
    case Expr::ADD: return a + b;
    case Expr::SUB: return a - b;
    case Expr::MUL: return a * b;
    case Expr::DIV: return a / b;
    default: break;
  }
  if (std::isnan(a) || std::isnan(b)) return NONE;  // null compares to nothing
  switch (fast) {
    case Expr::LT: return a < b;
    case Expr::LE: return a <= b;
    case Expr::GT: return a > b;
    case Expr::GE: return a >= b;
    case Expr::EQ: return a == b;
    default: return a != b;
  }
}

num Eval(const Expr& e, const num* bind) {
  switch (e.kind) {
    case Expr::VAR: return bind[e.var];
    case Expr::CONST: return e.value;
    case Expr::OP: {
      if (e.fast != Expr::NONE_) return FastEval(e.fast, Eval(e.args[0], bind), Eval(e.args[1], bind));
      num a[16];
      int n = e.args.size();
      for (int i = 0; i < n; i++) a[i] = Eval(e.args[i], bind);
      return e.fn->eval(a, n);
    }
  }
  return 0;
}

Expr ReadExpr(const Json& j, std::map<std::string, int>& vars) {
  Expr e;
  if (const Json* v = j.Get("var")) {
    e.kind = Expr::VAR;
    auto it = vars.find(v->str);
    if (it == vars.end()) it = vars.emplace(v->str, (int)vars.size()).first;
    e.var = it->second;
  } else if (const Json* c = j.Get("const")) {
    e.kind = Expr::CONST; e.value = c->num;
  } else if (j.Get("null")) {
    e.kind = Expr::CONST; e.value = NONE;
  } else {
    e.kind = Expr::OP; e.op = j.At("op").str;
    for (auto& a : j.At("args").arr) e.args.push_back(ReadExpr(a, vars));
    e.fn = FindFunction(e.op.c_str());
    if (!e.fn) Fail("unknown function " + e.op);
    e.fast = FastOp(e.op, e.args.size());
    int n = e.args.size();
    if (n > 16 || n < e.fn->min_args || (e.fn->max_args >= 0 && n > e.fn->max_args)) Fail("wrong number of arguments of " + e.op);
  }
  return e;
}

void ExprVars(const Expr& e, std::vector<int>& out) {
  if (e.kind == Expr::VAR) out.push_back(e.var);
  for (auto& a : e.args) ExprVars(a, out);
}

// ----------------------------------------------------------------------
// Rows: a relation is a flat array of fixed-width rows.
struct Rows {
  int width = 0;
  bool has_null = false;  // some field is NONE (inputs: an empty CSV field)
  std::vector<num> data;
  size_t size() const { return width ? data.size() / width : 0; }
  const num* row(size_t r) const { return &data[r * width]; }
  num* row(size_t r) { return &data[r * width]; }
  void push(const num* r) { data.insert(data.end(), r, r + width); }
};

// Index of rows by a subset of columns: key -> contiguous range in a
// copy of the rows grouped by key. One dense column: offsets (CSR);
// otherwise a hash of the packed key.
struct Index {
  std::vector<int> cols;
  bool csr = false;
  std::vector<uint32_t> offsets;
  std::unordered_map<uint64_t, std::pair<uint32_t, uint32_t>> ranges;
  Rows sorted;
  i64 min_key = 0;

  static uint64_t Pack(const num* row, const std::vector<int>& cols) {
    uint64_t h = 1469598103934665603ULL;
    for (int c : cols) { h ^= (uint64_t)(i64)row[c]; h *= 1099511628211ULL; h ^= h >> 29; }
    return h;
  }

  void Build(const Rows& R, const std::vector<int>& columns) {
    cols = columns;
    size_t n = R.size();
    int w = R.width;
    sorted.width = w;
    sorted.data.resize(n * w);
    if (cols.size() == 1) {
      int c = cols[0];
      i64 lo = 0, hi = -1;
      for (size_t r = 0; r < n; r++) { i64 k = (i64)R.row(r)[c]; if (r == 0 || k < lo) lo = k; if (r == 0 || k > hi) hi = k; }
      if (n && hi - lo < (i64)(4 * n + 1024)) {
        csr = true; min_key = lo;
        offsets.assign(hi - lo + 2, 0);
#pragma omp parallel for schedule(static)
        for (size_t r = 0; r < n; r++) __atomic_fetch_add(&offsets[(i64)R.row(r)[c] - lo + 1], 1u, __ATOMIC_RELAXED);
        for (size_t k = 1; k < offsets.size(); k++) offsets[k] += offsets[k - 1];
        std::vector<uint32_t> cur(offsets.begin(), offsets.end() - 1);
#pragma omp parallel for schedule(static)
        for (size_t r = 0; r < n; r++) {
          uint32_t pos = __atomic_fetch_add(&cur[(i64)R.row(r)[c] - lo], 1u, __ATOMIC_RELAXED);
          memcpy(&sorted.data[(size_t)pos * w], R.row(r), w * sizeof(num));
        }
        return;
      }
    }
    std::vector<std::pair<uint64_t, uint32_t>> keyed(n);
    for (size_t r = 0; r < n; r++) keyed[r] = {Pack(R.row(r), cols), (uint32_t)r};
    std::sort(keyed.begin(), keyed.end());
    ranges.reserve(n);
    for (size_t r = 0; r < n;) {
      size_t e = r;
      while (e < n && keyed[e].first == keyed[r].first) { memcpy(&sorted.data[e * w], R.row(keyed[e].second), w * sizeof(num)); e++; }
      ranges[keyed[r].first] = {(uint32_t)r, (uint32_t)e};
      r = e;
    }
  }

  // Range [begin, end) of positions in `sorted` matching the probe values
  // (probe[i] is the value of cols[i]).
  void Lookup(const num* probe, size_t* begin, size_t* end) const {
    *begin = *end = 0;
    if (csr) {
      i64 k = (i64)probe[0] - min_key;
      if (k < 0 || k + 1 >= (i64)offsets.size()) return;
      *begin = offsets[k]; *end = offsets[k + 1];
    } else {
      std::vector<int> id(cols.size()); for (size_t i = 0; i < id.size(); i++) id[i] = i;
      auto it = ranges.find(Pack(probe, id));
      if (it == ranges.end()) return;
      *begin = it->second.first; *end = it->second.second;
    }
  }
};

// ----------------------------------------------------------------------
// Atomics on doubles go through their bit patterns.
inline num AtomicLoad(const num* p) { uint64_t b = __atomic_load_n((const uint64_t*)p, __ATOMIC_RELAXED); num v; memcpy(&v, &b, 8); return v; }
inline void AtomicStore(num* p, num v) { uint64_t b; memcpy(&b, &v, 8); __atomic_store_n((uint64_t*)p, b, __ATOMIC_RELAXED); }
inline bool AtomicCas(num* p, num& expected, num desired) {
  uint64_t e, d; memcpy(&e, &expected, 8); memcpy(&d, &desired, 8);
  bool ok = __atomic_compare_exchange_n((uint64_t*)p, &e, d, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED);
  if (!ok) memcpy(&expected, &e, 8);
  return ok;
}
inline void AtomicAdd(num* p, num v) { num cur = AtomicLoad(p); while (!AtomicCas(p, cur, cur + v)) {} }

// A byte spinlock.
inline void Lock(uint8_t* l) { while (__atomic_exchange_n(l, (uint8_t)1, __ATOMIC_ACQUIRE)) {} }
inline void Unlock(uint8_t* l) { __atomic_store_n(l, (uint8_t)0, __ATOMIC_RELEASE); }

// Equality of value vectors in which null (NaN) equals null.
inline bool SameValues(const num* a, const num* b, int n) {
  for (int c = 0; c < n; c++) if (!(a[c] == b[c] || (std::isnan(a[c]) && std::isnan(b[c])))) return false;
  return true;
}
struct NanEqual {
  bool operator()(const std::vector<num>& a, const std::vector<num>& b) const {
    return a.size() == b.size() && SameValues(a.data(), b.data(), (int)a.size());
  }
};
struct KeyHash {
  size_t operator()(const std::vector<num>& k) const {
    uint64_t h = 1469598103934665603ULL;
    for (num x : k) { h ^= (uint64_t)(i64)x; h *= 1099511628211ULL; h ^= h >> 29; }
    return h;
  }
};

// ----------------------------------------------------------------------
// Aggregates of value columns.
enum Agg { MIN, MAX, ARGMIN, ARGMAX, SUM, ASSIGN, LIST, SET, COUNT, ARRAYAGG };

// List-like aggregates collect contributions and produce an arena value
// (or a count): always recomputed as a black box.
bool Collects(Agg a) { return a == LIST || a == SET || a == COUNT || a == ARRAYAGG; }

Agg ParseAgg(const std::string& a) {
  if (a == "list") return LIST;
  if (a == "set") return SET;
  if (a == "count") return COUNT;
  if (a == "arrayagg") return ARRAYAGG;
  if (a == "min") return MIN;
  if (a == "max") return MAX;
  if (a == "argmin") return ARGMIN;
  if (a == "argmax") return ARGMAX;
  if (a == "sum") return SUM;
  if (a == "assign") return ASSIGN;
  Fail("unknown aggregate " + a);
}

bool Lattice(Agg a) { return a == MIN || a == MAX || a == ARGMIN || a == ARGMAX; }

// The algebra of each aggregate: what a change may do to a stored value.
// Idempotent: a contribution can be merged as often as it arrives.
// Inverse: a changed contribution can be absorbed as a difference.
// Collects: the value is the multiset of contributions itself.
struct AggProps { bool idempotent, inverse, collects; const char* name; };
AggProps Props(Agg a) {
  switch (a) {
    case MIN: return {true, false, false, "Min"};
    case MAX: return {true, false, false, "Max"};
    case ARGMIN: return {true, false, false, "ArgMin"};
    case ARGMAX: return {true, false, false, "ArgMax"};
    case SUM: return {false, true, false, "Sum"};
    case ASSIGN: return {false, false, false, "="};
    case LIST: return {false, false, true, "List"};
    case SET: return {false, false, true, "Set"};
    case COUNT: return {false, false, true, "Count"};
    default: return {false, false, true, "Array"};
  }
}

// How an expression moves when variable v moves up and all else stays:
// 0 does not depend on v, 1 up, -1 down, 2 either way or unknown.
int MonoIn(const Expr& e, int v) {
  if (e.kind == Expr::VAR) return e.var == v ? 1 : 0;
  if (e.kind == Expr::CONST) return 0;
  auto comb = [](int a, int b) { if (a == 0) return b; if (b == 0) return a; return a == b ? a : 2; };
  auto neg = [](int a) { return a == 1 ? -1 : a == -1 ? 1 : a; };
  size_t n = e.args.size();
  if (e.op == "+") { int r = 0; for (auto& a : e.args) r = comb(r, MonoIn(a, v)); return r; }
  if (e.op == "-" && n == 2) return comb(MonoIn(e.args[0], v), neg(MonoIn(e.args[1], v)));
  if (e.op == "-" && n == 1) return neg(MonoIn(e.args[0], v));
  if (e.op == "*" && n == 2) {
    for (int i = 0; i < 2; i++) if (e.args[i].kind == Expr::CONST) { int m = MonoIn(e.args[1 - i], v); return e.args[i].value >= 0 ? m : neg(m); }
    return MonoIn(e.args[0], v) == 0 && MonoIn(e.args[1], v) == 0 ? 0 : 2;
  }
  if (e.op == "/" && n == 2) {
    if (MonoIn(e.args[1], v) != 0) return 2;
    if (e.args[1].kind == Expr::CONST) { int m = MonoIn(e.args[0], v); return e.args[1].value > 0 ? m : neg(m); }
    return MonoIn(e.args[0], v) == 0 ? 0 : 2;
  }
  if (e.op == "Least" || e.op == "Greatest") { int r = 0; for (auto& a : e.args) r = comb(r, MonoIn(a, v)); return r; }
  for (auto& a : e.args) if (MonoIn(a, v) != 0) return 2;
  return 0;
}

// ----------------------------------------------------------------------
// Slots of value vectors with per-slot flags, shared by the dense and the
// packed storage (the packed table maps keys to slots).
struct Slots {
  int nv = 0;
  std::vector<num> vals;        // slot * nv + column
  std::vector<num> vals_snap;   // values at round start
  std::vector<uint8_t> alive;   // 1: the key holds a value (2: being claimed)
  std::vector<uint8_t> alive_snap;
  std::vector<uint8_t> queued;  // key already in next_delta this round
  std::vector<uint8_t> dirty;   // key to recompute this round
  std::vector<uint8_t> lock;    // for multi-column updates
  void Resize(size_t n) {
    vals.resize(n * nv, 0); vals_snap.resize(n * nv, 0);
    alive.resize(n, 0); alive_snap.resize(n, 0); queued.resize(n, 0); dirty.resize(n, 0); lock.resize(n, 0);
  }
  void Snapshot() { vals_snap = vals; alive_snap = alive; }
};

// Open-addressing hash from a packed 64-bit key to a slot, insert-only,
// lock-free between rehashes (which happen between chunks of work).
struct PackedMap {
  static constexpr uint64_t EMPTY = ~uint64_t(0);
  static constexpr uint64_t RESERVED = ~uint64_t(0) - 1;
  static const int MAX_PROBE = 64;
  std::vector<uint64_t> keys;
  size_t count = 0, mask = 0;
  void Init(size_t cap) { keys.assign(cap, EMPTY); mask = cap - 1; count = 0; }
  static size_t Hash(uint64_t k) { k ^= k >> 33; k *= 0xff51afd7ed558ccdULL; k ^= k >> 33; k *= 0xc4ceb9fe1a85ec53ULL; k ^= k >> 33; return k; }
  size_t Find(uint64_t k) const {
    size_t i = Hash(k) & mask;
    while (keys[i] != EMPTY && keys[i] != k) i = (i + 1) & mask;
    return i;
  }
  // (slot, inserted); ~0 when the probe limit is hit.
  std::pair<size_t, bool> Insert(uint64_t k) {
    size_t i = Hash(k) & mask;
    for (int probe = 0; probe < MAX_PROBE; probe++, i = (i + 1) & mask) {
      uint64_t cur = __atomic_load_n(&keys[i], __ATOMIC_ACQUIRE);
      if (cur == EMPTY) {
        uint64_t expect = EMPTY;
        if (__atomic_compare_exchange_n(&keys[i], &expect, RESERVED, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
          __atomic_store_n(&keys[i], k, __ATOMIC_RELEASE);
          __atomic_fetch_add(&count, (size_t)1, __ATOMIC_RELAXED);
          return {i, true};
        }
        cur = expect;
      }
      while (cur == RESERVED) cur = __atomic_load_n(&keys[i], __ATOMIC_ACQUIRE);
      if (cur == k) return {i, false};
    }
    return {~size_t(0), false};
  }
};

// ----------------------------------------------------------------------
// A state relation: keys -> value columns, with this round's delta.
struct State {
  std::string name;
  int arity = 0;
  int nv = 0;                 // value columns
  std::vector<Agg> aggs;      // per value column
  std::vector<int> argof;     // ARGMIN/ARGMAX: the column it follows, else -1
  // How a change reaches this head: LATTICE pushes contributions (every
  // column a semilattice), GROUP pushes differences (every column a sum),
  // BLACKBOX recomputes the affected keys. The optimizations can be
  // switched off (SOCRATIC_LATTICE_OPT / SOCRATIC_GROUP_OPT = false).
  // SEMI: the contributions of every key are kept as a multiset; a change
  // replaces one of them and the key is folded again (no walk back).
  enum Tier { LATTICE, GROUP, BLACKBOX, SEMI } tier = BLACKBOX;
  std::vector<std::vector<num>> bag;  // SEMI: per slot, the contributions (nv values each)
  std::vector<int32_t> refs;          // SEMI presence states: how many bodies hold the key
  bool has_arg = false;       // multi-column updates need a per-key lock
  // A set whose facts can be retracted (its rules read a left atom or a
  // retractable state): stored as key -> 1, so that its log tells
  // retractions (NONE) from insertions and readers recompute.
  bool exists = false;
  bool retractable = false;   // readers must recompute, not push
  bool stop = false;          // a stop predicate: a row ends the run
  // A rule joining two states that change in the same pass: differences
  // pushed per changed atom double count their joint change, so the
  // keys are recomputed instead.
  bool joins_states = false;
  bool internal = false;      // not written out
  std::vector<Type> types;    // per column (keys, then values), for the output
  std::vector<bool> hidden;   // value columns not written (ArgMin's Min)
  num eps = 1e-12;
  int threads = 1;

  // Storage.
  bool dense = false;   // arity 1, small domain: slot = key - lo
  bool dense2 = false;  // arity 2 set over a small domain: bitmap
  bool packed = false;  // arity 2, 32-bit keys: hash to slots
  i64 lo = 0, n2 = 0;
  std::vector<uint64_t> bits2;
  Slots slots;
  PackedMap pmap;
  std::unordered_map<std::vector<num>, size_t, KeyHash> table;  // generic: key -> slot
  size_t count = 0;

  Rows delta, next_delta;   // next_delta: keys changed during the current evaluation
  Rows log;                 // closed changes (key, new, old) in pass order
  int order = 0;            // position in the diamond order
  std::vector<std::vector<num>> spill;       // packed rows past the probe limit
  std::vector<std::vector<num>> dirty_keys;  // per thread (black-box heads)

  int DeltaWidth() const { return arity + 2 * nv; }

  void Init(i64 domain_lo, i64 domain_hi, int nthreads, Tier t, bool computed_keys) {
    threads = nthreads;
    if (exists) { nv = 1; aggs.assign(1, ASSIGN); }
    slots.nv = nv;
    argof.assign(nv, -1);
    for (int c = 0; c < nv; c++) {
      if (aggs[c] == ARGMIN || aggs[c] == ARGMAX) {
        has_arg = true;
        for (int d = 0; d < nv; d++) if (d != c && aggs[d] == (aggs[c] == ARGMIN ? MIN : MAX)) { argof[c] = d; break; }
        if (argof[c] < 0) Fail("ArgMin/ArgMax column of " + name + " has no Min/Max column");
      }
    }
    tier = t;
    delta.width = next_delta.width = DeltaWidth();
    spill.resize(threads); dirty_keys.resize(threads); dirty_overflow.resize(threads);
    i64 span = domain_hi - domain_lo + 1;
    if (computed_keys) span = 0;  // keys may be anything: generic storage
    if (t == SEMI && arity != 1) span = 0;  // the bags follow slots, which the packed map moves on rehash
    if (arity == 1 && span > 0 && span < (i64)2000000000LL) {
      dense = true; lo = domain_lo; slots.Resize(span);
    } else if (arity == 2 && nv == 0 && t == LATTICE && span > 0 && span <= (1LL << 17) && span * span <= (1LL << 34)) {
      // The bitmap only takes offers; a recomputed set needs slots it can clear.
      dense2 = true; lo = domain_lo; n2 = span;
      bits2.assign((size_t)((span * span + 63) / 64), 0);
    } else if (arity == 2 && t != SEMI && domain_lo >= -(1LL << 31) && domain_hi < (1LL << 31)) {
      packed = true; pmap.Init(1 << 16); slots.Resize(1 << 16);
    }
  }

  static uint64_t PackKey(const num* row) { return ((uint64_t)(uint32_t)(i64)row[0] << 32) | (uint32_t)(i64)row[1]; }

  // Slot of a key, creating it (not alive) when absent; ~0 when the packed
  // probe limit is hit (the row is spilled). The generic path is only
  // used single-threaded.
  void CheckKey(const num* row) const {
    for (int c = 0; c < arity; c++) if (std::isnan(row[c])) Fail("null in a key column of " + name + " (not supported)");
  }
  size_t SlotOf(const num* row) {
    if (dense) { i64 k = (i64)row[0] - lo; if (k < 0 || k >= (i64)slots.alive.size()) Fail("key outside domain in " + name); return (size_t)k; }
    if (packed) return pmap.Insert(PackKey(row)).first;
    std::vector<num> key(row, row + arity);
    auto it = table.find(key);
    if (it != table.end()) return it->second;
    size_t s = table.size();
    table.emplace(std::move(key), s);
    slots.Resize(s + 1);
    return s;
  }
  size_t FindSlot(const num* row) const {
    if (dense) { i64 k = (i64)row[0] - lo; return (k < 0 || k >= (i64)slots.alive.size()) ? ~size_t(0) : (size_t)k; }
    if (packed) { size_t i = pmap.Find(PackKey(row)); return pmap.keys[i] == PackedMap::EMPTY ? ~size_t(0) : i; }
    auto it = table.find(std::vector<num>(row, row + arity));
    return it == table.end() ? ~size_t(0) : it->second;
  }

  bool Queue(size_t slot) { return __atomic_exchange_n(&slots.queued[slot], (uint8_t)1, __ATOMIC_RELAXED) == 0; }

  // Push: merges one contribution (key + nv values) into the state.
  // Returns true when the key is newly queued for the next round.
  // Lock-free for sets and independent columns; a per-key lock when a
  // column follows another (ArgMin).
  bool Offer(const num* row) {
    if (dense2) {
      i64 a = (i64)row[0] - lo, b = (i64)row[1] - lo;
      if (a < 0 || b < 0 || a >= n2 || b >= n2) Fail("key outside domain in " + name);
      uint64_t pos = (uint64_t)a * n2 + b, bit = uint64_t(1) << (pos & 63);
      if (__atomic_load_n(&bits2[pos >> 6], __ATOMIC_RELAXED) & bit) return false;
      return (__atomic_fetch_or(&bits2[pos >> 6], bit, __ATOMIC_RELAXED) & bit) == 0;
    }
    size_t s = SlotOf(row);
    if (s == ~size_t(0)) { std::vector<num>& S = spill[omp_get_thread_num()]; S.insert(S.end(), row, row + arity + nv); return false; }
    const num* v = row + arity;
    if (nv == 0) {
      if (__atomic_load_n(&slots.alive[s], __ATOMIC_RELAXED)) return false;
      if (__atomic_exchange_n(&slots.alive[s], (uint8_t)1, __ATOMIC_RELAXED)) return false;
      return Queue(s);
    }
    num* cur = &slots.vals[s * nv];
    if (has_arg) {
      Lock(&slots.lock[s]);
      bool changed = slots.alive[s] != 1;
      if (changed) { memcpy(cur, v, nv * sizeof(num)); slots.alive[s] = 1; }
      else {
        for (int c = 0; c < nv; c++) {
          if (argof[c] >= 0) continue;
          if (aggs[c] == SUM) { if (!std::isnan(v[c])) { cur[c] += v[c]; changed |= v[c] != 0; } }
          else if (aggs[c] == ASSIGN) { changed |= cur[c] != v[c]; cur[c] = v[c]; }
          else {
            // Ties go to the smaller argument: a deterministic ArgMin/ArgMax.
            bool better = aggs[c] == MIN ? v[c] < cur[c] : v[c] > cur[c];
            if (!better && v[c] == cur[c]) for (int d = 0; d < nv; d++) if (argof[d] == c && v[d] < cur[d]) better = true;
            if (better) {
              cur[c] = v[c]; changed = true;
              for (int d = 0; d < nv; d++) if (argof[d] == c) cur[d] = v[d];
            }
          }
        }
      }
      Unlock(&slots.lock[s]);
      return changed && Queue(s);
    }
    // Lock-free: a fresh key claims the slot (alive 0 -> 2), publishes 1.
    if (__atomic_load_n(&slots.alive[s], __ATOMIC_ACQUIRE) == 0) {
      uint8_t expect = 0;
      if (__atomic_compare_exchange_n(&slots.alive[s], &expect, (uint8_t)2, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
        for (int c = 0; c < nv; c++) AtomicStore(&cur[c], v[c]);
        __atomic_store_n(&slots.alive[s], (uint8_t)1, __ATOMIC_RELEASE);
        return Queue(s);
      }
    }
    while (__atomic_load_n(&slots.alive[s], __ATOMIC_ACQUIRE) != 1) {}
    bool changed = false;
    for (int c = 0; c < nv; c++) {
      switch (aggs[c]) {
        case SUM: if (!std::isnan(v[c])) { AtomicAdd(&cur[c], v[c]); changed |= v[c] != 0; } break;
        case ASSIGN: if (AtomicLoad(&cur[c]) != v[c]) { AtomicStore(&cur[c], v[c]); changed = true; } break;
        case MIN: case MAX: {
          num old = AtomicLoad(&cur[c]);
          bool better = aggs[c] == MIN ? v[c] < old : v[c] > old;
          while (better) {
            if (AtomicCas(&cur[c], old, v[c])) { changed = true; break; }
            better = aggs[c] == MIN ? v[c] < old : v[c] > old;
          }
          break;
        }
        default: break;
      }
    }
    return changed && Queue(s);
  }

  // Black box: sets a key's values to a recomputed aggregate (nullptr:
  // no contribution, the key disappears). One thread owns the key.
  bool Set(const num* row, const num* vals) {
    size_t s = SlotOf(row);
    if (s == ~size_t(0)) Fail("packed table overflow during recomputation of " + name);
    return SetSlot(s, vals);
  }
  bool SetSlot(size_t s, const num* vals) {
    num* cur = &slots.vals[s * nv];
    bool was = slots.alive[s] == 1;
    if (!vals) { if (was) { slots.alive[s] = 0; return Queue(s); } return false; }
    bool changed = !was;
    for (int c = 0; c < nv && !changed; c++) {
      num d = vals[c] - cur[c];
      changed = aggs[c] == SUM ? !(d > -eps && d < eps) : vals[c] != cur[c];
    }
    if (!changed) return false;
    memcpy(cur, vals, nv * sizeof(num));
    slots.alive[s] = 1;
    return Queue(s);
  }

  // Experiment (SOCRATES_STORE_CONTRIB): the contributions of every key are
  // kept, identified by the rule and the key columns of its body atoms; a
  // change replaces or removes its entry, and a key is folded from its list.
  std::vector<std::vector<std::pair<uint64_t, num>>> contribs;  // per slot
  void StoreContribution(const num* key, uint64_t id, num v, bool remove) {
    size_t s = SlotOf(key);
    if (s == ~size_t(0)) Fail("contribution store needs dense or packed keys");
    if (contribs.size() <= s) {
      Lock(&store_lock);
      if (contribs.size() <= s) contribs.resize(slots.alive.size());
      Unlock(&store_lock);
    }
    Lock(&slots.lock[s]);
    auto& L = contribs[s];
    size_t i = 0; while (i < L.size() && L[i].first != id) i++;
    if (remove) { if (i < L.size()) { L[i] = L.back(); L.pop_back(); } }
    else if (i < L.size()) L[i].second = v; else L.emplace_back(id, v);
    Unlock(&slots.lock[s]);
  }
  uint8_t store_lock = 0;

  // Experiment (SOCRATES_MARK_ALL): mark every present key, skipping the
  // delta join that finds the affected ones.
  void MarkAllAlive() {
    if (dense || packed) { for (size_t s = 0; s < slots.alive.size(); s++) if (slots.alive[s] == 1 && !slots.dirty[s]) { slots.dirty[s] = 1; std::vector<num>& D = dirty_keys[0]; if (dense) D.push_back((num)(lo + (i64)s)); else { D.push_back((num)(int32_t)(pmap.keys[s] >> 32)); D.push_back((num)(int32_t)(uint32_t)pmap.keys[s]); } } }
    else for (auto& kv : table) if (slots.alive[kv.second] == 1) { std::vector<num>& D = dirty_overflow[0]; D.insert(D.end(), kv.first.begin(), kv.first.end()); }
  }

  // Marks a key for recomputation; each key is listed once per round
  // (a flag in its slot). Keys the packed table cannot place yet, and
  // generic keys, go to a list deduplicated at Pull time.
  std::vector<std::vector<num>> dirty_overflow;
  uint8_t dirty0 = 0;  // the one key of a nullary state
  void MarkDirty(const num* keyrow) {
    if (arity == 0) { __atomic_store_n(&dirty0, (uint8_t)1, __ATOMIC_RELAXED); return; }
    int t = omp_get_thread_num();
    size_t s = ~size_t(0);
    if (dense) s = SlotOf(keyrow);
    else if (packed) s = pmap.Insert(PackKey(keyrow)).first;
    if (s == ~size_t(0)) { std::vector<num>& O = dirty_overflow[t]; O.insert(O.end(), keyrow, keyrow + arity); return; }
    if (__atomic_exchange_n(&slots.dirty[s], (uint8_t)1, __ATOMIC_RELAXED)) return;
    std::vector<num>& D = dirty_keys[t];
    D.insert(D.end(), keyrow, keyrow + arity);
  }

  // Between chunks: grows the packed table when needed, re-offers spills.
  void Maintain(std::vector<num>& delta_out) {
    if (!packed) return;
    size_t spilled = 0;
    for (auto& S : spill) spilled += S.size() / (arity + nv);
    size_t need = pmap.count + spilled;
    if (need * 2 > pmap.keys.size() || spilled) {
      size_t cap = pmap.keys.size();
      while (need * 2 > cap) cap <<= 1;
      if (spilled && cap == pmap.keys.size()) cap <<= 1;
      Rehash(cap);
    }
    int w = arity + nv;
    for (auto& S : spill) {
      for (size_t i = 0; i < S.size(); i += w)
        // delta_out holds pushed head rows (key + values): Collect widens them.
        if (Offer(&S[i])) { delta_out.insert(delta_out.end(), &S[i], &S[i] + arity); for (int c = 0; c < nv; c++) delta_out.push_back(0); }
      S.clear();
    }
  }

  void Rehash(size_t cap) {
    PackedMap old; old.keys.swap(pmap.keys);
    Slots os = slots;
    pmap.Init(cap); slots.Resize(0); slots.Resize(cap);
    for (size_t i = 0; i < old.keys.size(); i++) if (old.keys[i] != PackedMap::EMPTY) {
      size_t j = PackedMap::Hash(old.keys[i]) & pmap.mask;
      while (pmap.keys[j] != PackedMap::EMPTY) j = (j + 1) & pmap.mask;
      pmap.keys[j] = old.keys[i]; pmap.count++;
      for (int c = 0; c < nv; c++) { slots.vals[j * nv + c] = os.vals[i * nv + c]; slots.vals_snap[j * nv + c] = os.vals_snap[i * nv + c]; }
      slots.alive[j] = os.alive[i]; slots.alive_snap[j] = os.alive_snap[i]; slots.queued[j] = os.queued[i]; slots.dirty[j] = os.dirty[i];
    }
  }

  void Snapshot() { if (nv) slots.Snapshot(); }

  // Delta rows for the next round: fills new and old values, drops keys
  // whose values did not move (sums, assignments), clears the flags.
  void CloseRound() {
    Rows& D = next_delta;
    size_t n = D.size();
    int w = D.width;
    if (dense2) { log.width = w; log.data.insert(log.data.end(), D.data.begin(), D.data.end()); D.data.clear(); return; }
    size_t kept = 0;
    for (size_t i = 0; i < n; i++) {
      num* row = D.row(i);
      size_t s = FindSlot(row);
      slots.queued[s] = 0;
      bool keep = true;
      if (nv) {
        bool alive = slots.alive[s] == 1, was = slots.alive_snap[s] == 1;
        for (int c = 0; c < nv; c++) {
          row[arity + c] = alive ? slots.vals[s * nv + c] : NONE;
          row[arity + nv + c] = was ? slots.vals_snap[s * nv + c] : NONE;
        }
        if (alive && was) {
          keep = false;
          for (int c = 0; c < nv; c++) {
            num d = row[arity + c] - row[arity + nv + c];
            keep |= aggs[c] == SUM ? !(d > -eps && d < eps) : row[arity + c] != row[arity + nv + c];
          }
        } else keep = alive || was;
      }
      if (keep) { if (kept != i) memcpy(D.row(kept), row, w * sizeof(num)); kept++; }
    }
    D.data.resize(kept * w);
    log.width = w;
    log.data.insert(log.data.end(), D.data.begin(), D.data.end());
    D.data.clear();
  }

  Rows Materialize() {
    Rows R; R.width = arity + nv;
    count = 0;
    if (dense2) {
      for (size_t w = 0; w < bits2.size(); w++) count += __builtin_popcountll(bits2[w]);
      R.data.reserve(count * 2);
      for (size_t w = 0; w < bits2.size(); w++) {
        uint64_t word = bits2[w];
        while (word) {
          int t = __builtin_ctzll(word); word &= word - 1;
          uint64_t pos = (uint64_t)w * 64 + t;
          R.data.push_back((num)(lo + (i64)(pos / n2))); R.data.push_back((num)(lo + (i64)(pos % n2)));
        }
      }
      return R;
    }
    auto emit = [&](size_t s, num k0, num k1) {
      if (slots.alive[s] != 1) return;
      R.data.push_back(k0); if (arity == 2) R.data.push_back(k1);
      for (int c = 0; c < nv; c++) R.data.push_back(slots.vals[s * nv + c]);
      count++;
    };
    if (dense) { for (size_t s = 0; s < slots.alive.size(); s++) emit(s, (num)(lo + (i64)s), 0); }
    else if (packed) {
      for (size_t s = 0; s < pmap.keys.size(); s++) if (pmap.keys[s] != PackedMap::EMPTY)
        emit(s, (num)(int32_t)(pmap.keys[s] >> 32), (num)(int32_t)(uint32_t)pmap.keys[s]);
    } else {
      for (auto& kv : table) {
        if (slots.alive[kv.second] != 1) continue;
        R.data.insert(R.data.end(), kv.first.begin(), kv.first.end());
        for (int c = 0; c < nv; c++) R.data.push_back(slots.vals[kv.second * nv + c]);
        count++;
      }
    }
    return R;
  }
};

// ----------------------------------------------------------------------
struct Atom {
  std::string rel;
  std::vector<Expr> args;  // per column; kind OP with op "_" = unused
  bool recursive = false;
  bool has_value = false;  // the last argument reads the value column
  // An aggregating expression of the body, hoisted into a state keyed by
  // its outer variables: looked up by key, null (NONE) when absent.
  bool left = false;
  // `x in list`: args are the list expression and the element variable.
  bool unnest = false;
};

struct Rule {
  std::string head;
  std::vector<Expr> keys;
  std::vector<Expr> values;  // one per value column of the head
  std::vector<Atom> atoms;
  std::vector<Expr> conds;
  std::vector<std::pair<int, Expr>> lets;
  int nvars = 0;
};

// An evaluation plan: atoms in execution order, the index each one is
// looked up through, and the conditions resolved per stage.
struct Plan {
  const Rule* rule;
  std::vector<int> order;
  std::vector<const Rows*> src;
  std::vector<const Index*> idx;
  std::vector<std::vector<int>> bound_cols, bind_cols, const_cols;
  std::vector<std::vector<int>> conds_after, lets_after;
  std::vector<std::vector<int>> checks_after;  // lets whose variable was bound already: equalities
  std::vector<int> preset;   // variables bound before the first atom
  int delta_pos = -1;        // execution position of the delta atom
  std::vector<num> null_row; // the row a left atom yields when its key is absent
  bool may_null = false;     // a variable may be NONE: a left atom, a value column, a null input
  bool makes_values = false; // an expression adds to the arena: evaluated single-threaded
  std::vector<int> head_var; // per head column: the variable it copies, or -1 (an expression)
  // Point lookups: an atom of a state whose key columns are all bound is
  // read from the state itself by key, with no materialized copy or index.
  std::vector<const State*> point;
  std::vector<char> point_before;  // the lookup first consults the before-overlay
};

typedef void (*PassCallback)(int pass, long long changed);

bool CreatesValues(const Expr& e) {
  if (e.kind == Expr::OP && ::CreatesValues(e.op.c_str())) return true;
  for (auto& a : e.args) if (CreatesValues(a)) return true;
  return false;
}

struct Engine {
  int threads = 1;
  // How the component is evaluated. Differential: changes are pushed into
  // the heads, each by its tier. Recompute: every predicate is evaluated
  // whole on every pass. One mode for the whole component.
  enum Mode { DIFFERENTIAL, RECOMPUTE } mode = DIFFERENTIAL;
  std::map<std::string, std::string> why;  // per state: the tier and the reason
  Arena arena;
  Dictionary dict;
  std::map<std::string, std::vector<Type>> input_types;
  PassCallback on_pass = nullptr;  // told the pass number and changed facts
  std::map<std::string, Rows> inputs;
  std::map<std::string, const Rows*> scan_rows;
  std::map<std::string, State> states;
  std::vector<Rule> rules;
  std::map<std::pair<std::string, std::vector<int>>, std::unique_ptr<Index>> input_index;
  std::map<std::string, Rows> full_state;  // materialized at round start
  // A nonlinear semigroup rule consumes the changes of its atoms one atom
  // at a time: the i-th atom's changes against the atoms before it as they
  // were before their own changes, and the atoms after it as they are now.
  std::map<std::string, Rows> before_state;  // a state with a range of its log reverted
  std::map<std::string, std::unordered_map<std::vector<num>, std::vector<num>, KeyHash>> before_overlay;  // key -> old row (empty: absent)
  std::set<int> plan_before_atoms;           // atoms of the rule being planned that read before_state
  bool plan_point_lookups = false;           // MakePlan may read states by key (semigroup heads)
  // The materialized copy of a state, made when first needed in a visit.
  const Rows& FullState(const std::string& name) {
    auto it = full_state.find(name);
    if (it == full_state.end()) it = full_state.emplace(name, states.at(name).Materialize()).first;
    return it->second;
  }
  std::map<std::pair<std::string, std::vector<int>>, std::unique_ptr<Index>> state_index;  // per round
  i64 domain_lo = 0, domain_hi = 0;
  double index_s = 0;
  bool trace = getenv("SOCRATES_TRACE") != nullptr;
  bool mark_all = getenv("SOCRATES_MARK_ALL") != nullptr;  // experiment: see MarkAllAlive
  // Semigroup predicates recomputed in full every pass (every rule run
  // whole, contributions folded by key), as the SQL path does: no delta
  // join, no marking, new keys found by construction.
  bool semigroup_full = !(getenv("SOCRATES_SEMIGROUP") && !strcmp(getenv("SOCRATES_SEMIGROUP"), "walks"));  // the historical two-walk path on request
  bool store_contrib = getenv("SOCRATES_STORE_CONTRIB") != nullptr;  // experiment: see StoreContribution
  const size_t CHUNK = 1 << 18;
  const size_t BLOCK = 256;  // delta rows per unit of parallel work

  // ---------------------------------------------------------------- input
  Rows ReadCsv(const std::string& path, int width) {
    Rows R; R.width = width;
    int fd = open(path.c_str(), O_RDONLY);
    if (fd < 0) Fail("cannot open " + path);
    struct stat st; fstat(fd, &st);
    size_t n = st.st_size;
    if (n == 0) { close(fd); return R; }
    const char* data = (const char*)mmap(nullptr, n, PROT_READ, MAP_PRIVATE, fd, 0);
    size_t start = 0;
    {
      size_t i = 0;
      if (i < n && data[i] == '-') i++;
      bool numeric = i < n && data[i] >= '0' && data[i] <= '9';
      if (!numeric) { while (start < n && data[start] != '\n') start++; if (start < n) start++; }
    }
    std::vector<size_t> lo_of(threads + 1), count(threads + 1, 0);
    for (int t = 0; t <= threads; t++) {
      size_t lo = start + (n - start) * t / threads;
      if (t > 0 && t < threads) while (lo < n && data[lo - 1] != '\n') lo++;
      lo_of[t] = t == threads ? n : lo;
    }
#pragma omp parallel for num_threads(threads) schedule(static)
    for (int t = 0; t < threads; t++) {
      size_t c = 0;
      for (size_t i = lo_of[t]; i < lo_of[t + 1]; i++) c += data[i] == '\n';
      if (lo_of[t + 1] > lo_of[t] && data[lo_of[t + 1] - 1] != '\n') c++;
      count[t + 1] = c;
    }
    for (int t = 0; t < threads; t++) count[t + 1] += count[t];
    R.data.resize(count[threads] * width);
#pragma omp parallel for num_threads(threads) schedule(static)
    for (int t = 0; t < threads; t++) {
      size_t lo = lo_of[t], hi = lo_of[t + 1];
      num* out = R.data.data() + count[t] * width;
      size_t i = lo;
      while (i < hi) {
        for (int c = 0; c < width; c++) {
          size_t j = i; bool neg = false; i64 v = 0; num result;
          if (j < hi && data[j] == '-') { neg = true; j++; }
          while (j < hi && data[j] >= '0' && data[j] <= '9') v = v * 10 + (data[j++] - '0');
          result = neg ? -v : v;
          if (j == i && (j == hi || data[j] == ',' || data[j] == '\n' || data[j] == '\r')) { result = NONE; R.has_null = true; }  // empty: null
          else if (j < hi && data[j] != ',' && data[j] != '\n' && data[j] != '\r') {
            const char* e; result = strtod(data + i, (char**)&e); j = e - data;
          }
          *out++ = result;
          i = j;
          while (i < hi && data[i] != ',' && data[i] != '\n') i++;
          if (i < hi && data[i] == ',') i++;
        }
        while (i < hi && data[i] != '\n') i++;
        i++;
      }
    }
    munmap((void*)data, n); close(fd);
    return R;
  }

  const Rows& InputRows(const std::string& rel) {
    auto it = scan_rows.find(rel);
    return it != scan_rows.end() ? *it->second : inputs.at(rel);
  }

  const Index& InputIndex(const std::string& rel, const std::vector<int>& cols) {
    auto key = std::make_pair(rel, cols);
    auto it = input_index.find(key);
    if (it == input_index.end()) {
      auto idx = std::make_unique<Index>();
      double t = Now();
      idx->Build(InputRows(rel), cols);
      index_s += Now() - t;
      if (!scan_rows.count(rel)) {
        Rows().data.swap(inputs.at(rel).data);  // the sorted copy replaces the rows
        scan_rows[rel] = &idx->sorted;
      }
      it = input_index.emplace(key, std::move(idx)).first;
    }
    return *it->second;
  }

  const Index& StateIndex(const std::string& name, const std::vector<int>& cols, const Rows& rows) {
    auto key = std::make_pair(name, cols);
    auto it = state_index.find(key);
    if (it == state_index.end()) {
      auto idx = std::make_unique<Index>();
      idx->Build(rows, cols);
      it = state_index.emplace(key, std::move(idx)).first;
    }
    return *it->second;
  }

  // --------------------------------------------------------------- plans
  // `delta_at` (atom index or -1) reads the delta and goes first; `preset`
  // variables are bound before the first atom, and an atom binding one of
  // them is moved first (recomputation of a key).
  Plan MakePlan(const Rule& rule, int delta_at, const std::vector<int>& preset, bool mark = false) {
    Plan p; p.rule = &rule; p.preset = preset;
    int natoms = rule.atoms.size();
    // Marking affected keys: a condition on a value that may be null in
    // the delta (a retracted fact, an absent left atom) must not filter
    // the candidates; it is checked on recomputation.
    std::vector<char> nullable(rule.nvars, 0);
    if (mark) {
      for (int a = 0; a < natoms; a++) {
        const Atom& atom = rule.atoms[a];
        if (!(atom.left || a == delta_at) || !atom.recursive) continue;
        int arity = states.at(atom.rel).arity;
        for (size_t c = arity; c < atom.args.size(); c++) if (atom.args[c].kind == Expr::VAR) nullable[atom.args[c].var] = 1;
      }
      for (bool changed = true; changed;) {
        changed = false;
        for (auto& l : rule.lets) {
          if (nullable[l.first]) continue;
          std::vector<int> vs; ExprVars(l.second, vs);
          for (int v : vs) if (nullable[v]) { nullable[l.first] = 1; changed = true; }
        }
      }
    }
    size_t max_width = 0;
    for (auto& a : rule.atoms) max_width = std::max(max_width, a.args.size());
    p.null_row.assign(max_width, NONE);
    for (int a = 0; a < natoms; a++) p.order.push_back(a);
    if (delta_at >= 0) {
      // The changed atom goes first. After it the atoms keep the written
      // order, except that an atom none of whose columns is bound yet waits
      // for one that is: a scan of it per changed row would be a product.
      std::vector<int> rest; for (int a = 0; a < natoms; a++) if (a != delta_at) rest.push_back(a);
      std::vector<char> bound(rule.nvars, 0);
      auto mark = [&](int a) { for (auto& e : rule.atoms[a].args) if (e.kind == Expr::VAR) bound[e.var] = 1; if (rule.atoms[a].unnest) bound[rule.atoms[a].args[1].var] = 1; };
      mark(delta_at);
      p.order.clear(); p.order.push_back(delta_at); p.delta_pos = 0;
      while (!rest.empty()) {
        int pick = -1;
        for (size_t i = 0; i < rest.size() && pick < 0; i++) {
          const Atom& atom = rule.atoms[rest[i]];
          bool ok = false;
          if (atom.unnest) { std::vector<int> vs; ExprVars(atom.args[0], vs); ok = true; for (int v : vs) ok &= bound[v]; }
          else for (auto& e : atom.args) if (e.kind == Expr::CONST || (e.kind == Expr::VAR && bound[e.var])) ok = true;
          if (ok) pick = i;
        }
        if (pick < 0) pick = 0;
        p.order.push_back(rest[pick]); mark(rest[pick]); rest.erase(rest.begin() + pick);
      }
    }
    else if (!preset.empty()) {
      int best = -1;
      for (int a = 0; a < natoms; a++) {
        bool binds = false;
        for (auto& e : rule.atoms[a].args) if (e.kind == Expr::VAR) for (int v : preset) binds |= e.var == v;
        if (rule.atoms[a].left || rule.atoms[a].unnest) continue;  // looked up, never scanned
        if (binds && (best < 0 || (rule.atoms[best].recursive && !rule.atoms[a].recursive))) best = a;
      }
      if (best > 0) { p.order.erase(p.order.begin() + best); p.order.insert(p.order.begin(), best); }
    }
    std::vector<char> is_bound(rule.nvars, 0);
    for (int v : preset) is_bound[v] = 1;
    p.src.resize(natoms); p.idx.assign(natoms, nullptr); p.point.assign(natoms, nullptr); p.point_before.assign(natoms, 0);
    p.bound_cols.resize(natoms); p.bind_cols.resize(natoms); p.const_cols.resize(natoms);
    p.conds_after.resize(natoms + 1); p.lets_after.resize(natoms + 1); p.checks_after.resize(natoms + 1);
    std::vector<char> let_done(rule.lets.size(), 0);
    auto resolve = [&](int stage) {
      bool changed = true;
      while (changed) {
        changed = false;
        for (size_t l = 0; l < rule.lets.size(); l++) {
          if (let_done[l]) continue;
          std::vector<int> vs; ExprVars(rule.lets[l].second, vs);
          bool ok = true; for (int v : vs) if (!is_bound[v]) ok = false;
          if (!ok) continue;
          let_done[l] = 1; changed = true;
          if (!is_bound[rule.lets[l].first]) { is_bound[rule.lets[l].first] = 1; p.lets_after[stage].push_back(l); continue; }
          // The variable is bound already: the let is an equality to check
          // (skipped when marking, like a condition on a nullable value).
          bool null_side = nullable[rule.lets[l].first]; for (int v : vs) null_side |= nullable[v];
          if (!null_side) p.checks_after[stage].push_back(l);
        }
      }
      for (size_t c = 0; c < rule.conds.size(); c++) {
        bool placed = false;
        for (int s = 0; s < stage; s++) for (int x : p.conds_after[s]) if (x == (int)c) placed = true;
        if (placed) continue;
        std::vector<int> vs; ExprVars(rule.conds[c], vs);
        bool ok = true; for (int v : vs) if (!is_bound[v] || nullable[v]) ok = false;
        if (ok) p.conds_after[stage].push_back(c);
      }
    };
    resolve(0);
    for (int pos = 0; pos < natoms; pos++) {
      int a = p.order[pos];
      const Atom& atom = rule.atoms[a];
      if (atom.unnest) {
        std::vector<int> vs; ExprVars(atom.args[0], vs);
        for (int v : vs) if (!is_bound[v]) Fail("the list of an `in` of " + rule.head + " is not bound before it");
        int v = atom.args[1].var;
        if (is_bound[v]) p.bound_cols[pos].push_back(1); else { p.bind_cols[pos].push_back(1); is_bound[v] = 1; }
        resolve(pos + 1);
        continue;
      }
      for (size_t c = 0; c < atom.args.size(); c++) {
        const Expr& e = atom.args[c];
        if (e.kind == Expr::CONST) p.const_cols[pos].push_back(c);
        else if (e.kind == Expr::VAR) {
          if (is_bound[e.var]) p.bound_cols[pos].push_back(c);
          else { p.bind_cols[pos].push_back(c); is_bound[e.var] = 1; }
        }
      }
      std::vector<int> index_cols = p.bound_cols[pos];
      for (int c : p.const_cols[pos]) index_cols.push_back(c);
      std::sort(index_cols.begin(), index_cols.end());
      bool lookup = !index_cols.empty() && (pos > 0 || !preset.empty());
      if (atom.left && pos != p.delta_pos) {
        // Looked up by its key columns; a bound value column is checked after.
        int arity = states.at(atom.rel).arity;
        std::vector<int> keys;
        for (int c : index_cols) if (c < arity) keys.push_back(c);
        if ((int)keys.size() != arity) Fail("an aggregating expression of " + rule.head + " has a key that is not bound by the body");
        index_cols = keys; lookup = true;
      }
      if (atom.recursive) {
        bool before = pos != p.delta_pos && plan_before_atoms.count(a) > 0;
        const State& St = states.at(atom.rel);
        bool keys_bound = pos != p.delta_pos && plan_point_lookups && !St.dense2;
        for (int c = 0; c < St.arity && keys_bound; c++) {
          bool b = false;  // bound before this atom (its own bindings do not count)
          for (int x : p.bound_cols[pos]) b |= x == c;
          for (int x : p.const_cols[pos]) b |= x == c;
          keys_bound = b;
        }
        if (keys_bound) { p.point[pos] = &St; p.point_before[pos] = before; p.src[pos] = nullptr; resolve(pos + 1); continue; }
        if (before && !before_state.count(atom.rel)) before_state[atom.rel] = BeforeFromOverlay(St);
        const Rows& rows = pos == p.delta_pos ? St.delta : before ? before_state.at(atom.rel) : FullState(atom.rel);
        p.src[pos] = &rows;
        if (lookup) p.idx[pos] = &StateIndex(atom.rel + (pos == p.delta_pos ? "#delta" : before ? "#before" : "#full"), index_cols, rows);
      } else {
        if (lookup) p.idx[pos] = &InputIndex(atom.rel, index_cols);
      }
      resolve(pos + 1);
    }
    for (int pos = 0; pos < natoms; pos++) {
      int a = p.order[pos];
      if (!rule.atoms[a].recursive && !rule.atoms[a].unnest) p.src[pos] = &InputRows(rule.atoms[a].rel);
    }
    // Scan order: a fully scanned first atom is read grouped by the column
    // later atoms look up through, so those lookups walk memory in order.
    if (!p.idx[0] && natoms > 1 && !rule.atoms[p.order[0]].recursive && !rule.atoms[p.order[0]].unnest) {
      int scan_col = -1;
      for (int pos = 1; pos < natoms && scan_col < 0; pos++)
        for (int c : p.bound_cols[pos]) {
          int v = rule.atoms[p.order[pos]].args[c].var;
          for (int c0 : p.bind_cols[0]) if (rule.atoms[p.order[0]].args[c0].var == v) { scan_col = c0; break; }
          if (scan_col >= 0) break;
        }
      if (scan_col >= 0) p.src[0] = &InputIndex(rule.atoms[p.order[0]].rel, {scan_col}).sorted;
    }
    std::vector<int> head_vars;
    for (auto& k : rule.keys) ExprVars(k, head_vars);
    for (auto& v : rule.values) ExprVars(v, head_vars);
    for (int v : head_vars) if (!is_bound[v]) Fail("unbound head variable in a rule of " + rule.head);
    for (auto& k : rule.keys) p.head_var.push_back(k.kind == Expr::VAR ? k.var : -1);
    for (auto& v : rule.values) p.head_var.push_back(v.kind == Expr::VAR ? v.var : -1);
    for (auto& atom : rule.atoms) {
      if (atom.left || atom.has_value || atom.unnest) p.may_null = true;
      else if (atom.recursive) { if (states.at(atom.rel).nv) p.may_null = true; }
      else if (InputRows(atom.rel).has_null) p.may_null = true;
      for (auto& e : atom.args) if (CreatesValues(e)) p.makes_values = true;
    }
    for (auto& e : rule.keys) if (CreatesValues(e)) p.makes_values = true;
    for (auto& e : rule.values) if (CreatesValues(e)) p.makes_values = true;
    for (auto& e : rule.conds) if (CreatesValues(e)) p.makes_values = true;
    for (auto& l : rule.lets) if (CreatesValues(l.second)) p.makes_values = true;
    return p;
  }

  // Runs the plan over rows [r_begin, r_end) of the first atom's source
  // (its index range instead when preset variables bind it), calling
  // emit() at every full match with the variables bound. Serial.
  template <class Emit>
  void RunPlan(const Plan& p, size_t r_begin, size_t r_end, std::vector<num>& bind, Emit emit) {
    const Rule& rule = *p.rule;
    int natoms = rule.atoms.size();
    num probe[8];
    struct Frame { const num* base; int width; size_t r; size_t n; bool null_once; };
    std::vector<Frame> st(natoms);
    const num* null_row = p.null_row.data();
    size_t pw = p.null_row.size() + 1;
    std::vector<num> prow(natoms * pw);  // rows synthesized by point lookups
    auto check_atom = [&](int pos, const num* row) -> bool {
      const Atom& atom = rule.atoms[p.order[pos]];
      if (atom.unnest) {
        int v = atom.args[1].var;
        if (!p.bound_cols[pos].empty()) return Bits(bind[v]) == Bits(row[0]);
        bind[v] = row[0];
        return true;
      }
      if (row == null_row) {
        // Keys matched by construction; a bound value column does not.
        int arity = states.at(atom.rel).arity;
        for (int c : p.bound_cols[pos]) if (c >= arity) return false;
        for (int c : p.bind_cols[pos]) bind[atom.args[c].var] = NONE;
        return true;
      }
      for (int c : p.const_cols[pos]) if (row[c] != atom.args[c].value) return false;
      for (int c : p.bound_cols[pos]) if (row[c] != bind[atom.args[c].var]) return false;
      for (int c : p.bind_cols[pos]) bind[atom.args[c].var] = row[c];
      return true;
    };
    auto after = [&](int stage) -> bool {
      for (int l : p.lets_after[stage]) bind[rule.lets[l].first] = Eval(rule.lets[l].second, bind.data());
      for (int l : p.checks_after[stage]) { num v = Eval(rule.lets[l].second, bind.data()); if (std::isnan(v) || v != bind[rule.lets[l].first]) return false; }
      for (int c : p.conds_after[stage]) if (!Truthy(Eval(rule.conds[c], bind.data()))) return false;
      return true;
    };
    auto open = [&](int pos) {
      Frame& f = st[pos];
      f.null_once = false;
      const Atom& atom = rule.atoms[p.order[pos]];
      if (atom.unnest) {
        num list = Eval(atom.args[0], bind.data());
        f.width = 1; f.r = 0;
        if (arena.Valid(list) && arena.KindOf(list) == Arena::ARRAY) { f.base = arena.Elems(list); f.n = arena.Size(list); }
        else { f.base = nullptr; f.n = 0; }
        return;
      }
      if (p.point[pos]) {
        const State& St = *p.point[pos];
        int a = St.arity, nv = St.nv;
        num* row = &prow[pos * pw];
        for (int c = 0; c < a; c++) { const Expr& e = atom.args[c]; row[c] = e.kind == Expr::CONST ? e.value : bind[e.var]; }
        f.base = row; f.width = a + nv; f.r = 0; f.n = 0;
        bool found = false, decided = false;
        if (p.point_before[pos]) {
          auto ov = before_overlay.find(St.name);
          if (ov != before_overlay.end()) {
            auto it = ov->second.find(std::vector<num>(row, row + a));
            if (it != ov->second.end()) { decided = true; if (!it->second.empty()) { found = true; for (int c = 0; c < nv; c++) row[a + c] = it->second[a + c]; } }
          }
        }
        if (!decided) {
          size_t slot = St.FindSlot(row);
          if (slot != ~size_t(0) && St.slots.alive[slot] == 1) { found = true; for (int c = 0; c < nv; c++) row[a + c] = St.slots.vals[slot * nv + c]; }
        }
        if (found) f.n = 1;
        else if (atom.left && pos != p.delta_pos) f.null_once = true;
        return;
      }
      if (p.idx[pos]) {
        const Index& I = *p.idx[pos];
        for (size_t i = 0; i < I.cols.size(); i++) {
          const Expr& e = rule.atoms[p.order[pos]].args[I.cols[i]];
          probe[i] = e.kind == Expr::CONST ? e.value : bind[e.var];
        }
        I.Lookup(probe, &f.r, &f.n); f.base = I.sorted.data.data(); f.width = I.sorted.width;
        if (f.r == f.n && atom.left && pos != p.delta_pos) f.null_once = true;
      } else {
        // Only the first atom is split into [r_begin, r_end) between
        // threads; a later atom without an index is scanned whole.
        f.base = p.src[pos]->data.data(); f.width = p.src[pos]->width;
        f.r = pos == 0 ? r_begin : 0;
        f.n = pos == 0 ? r_end : p.src[pos]->size();
      }
    };
    auto next_row = [&](int pos) -> const num* {
      Frame& f = st[pos];
      if (f.null_once) { f.null_once = false; return null_row; }
      if (f.r == f.n) return nullptr; return f.base + (f.r++) * f.width;
    };
    if (!after(0)) return;
    if (natoms == 0) { emit(nullptr); return; }  // a fact rule: one match
    open(0);
    int pos = 0;
    while (pos >= 0) {
      const num* row = next_row(pos);
      if (!row) { pos--; continue; }
      if (!check_atom(pos, row)) continue;
      if (!after(pos + 1)) continue;
      if (pos + 1 == natoms) emit(st[0].base + (st[0].r - 1) * st[0].width);
      else { pos++; open(pos); }
    }
  }

  // The general walk over the bodies of a rule, compactly: every position
  // of the plan is a fixed record (scan, CSR lookup or hash lookup; the
  // columns to check and to bind as small arrays), the rows found are
  // kept by position, and the head reads its variables from one binding
  // array. Lets and conditions are evaluated at their stage as in
  // RunPlan. Unnest, point lookups and left atoms stay with RunPlan.
  struct FastLevel {
    int kind = 0;                      // 0 scan, 1 CSR lookup, 2 hash lookup
    const num* base = nullptr; int width = 0; size_t n = 0;
    const Index* I = nullptr;
    int nprobe = 0; int probe_var[4]; num probe_const[4];     // var < 0: the constant
    int ncheck = 0; int check_col[8]; int check_var[8]; num check_const[8];
    int nbind = 0; int bind_col[8]; int bind_var[8];
  };
  bool FastLevels(const Plan& p, std::vector<FastLevel>& L) {
    const Rule& rule = *p.rule;
    int natoms = rule.atoms.size();
    if (natoms == 0 || natoms > 8 || !p.preset.empty()) return false;
    L.assign(natoms, FastLevel());
    for (int pos = 0; pos < natoms; pos++) {
      const Atom& atom = rule.atoms[p.order[pos]];
      if (atom.unnest || atom.left || p.point[pos]) return false;
      FastLevel& f = L[pos];
      std::vector<char> covered(atom.args.size(), 0);  // columns the lookup matches exactly
      if (p.idx[pos]) {
        const Index& I = *p.idx[pos];
        if (I.cols.size() > 4) return false;
        f.kind = I.csr ? 1 : 2; f.I = &I; f.base = I.sorted.data.data(); f.width = I.sorted.width; f.n = I.sorted.size();
        f.nprobe = I.cols.size();
        for (int i = 0; i < f.nprobe; i++) {
          const Expr& e = atom.args[I.cols[i]];
          f.probe_var[i] = e.kind == Expr::CONST ? -1 : e.var; f.probe_const[i] = e.kind == Expr::CONST ? e.value : 0;
          if (I.csr) covered[I.cols[i]] = 1;  // a hash range may hold other keys: those are checked
        }
      } else { f.base = p.src[pos]->data.data(); f.width = p.src[pos]->width; f.n = p.src[pos]->size(); }
      for (int c : p.const_cols[pos]) if (!covered[c]) { if (f.ncheck == 8) return false; f.check_col[f.ncheck] = c; f.check_var[f.ncheck] = -1; f.check_const[f.ncheck] = atom.args[c].value; f.ncheck++; }
      for (int c : p.bound_cols[pos]) if (!covered[c]) { if (f.ncheck == 8) return false; f.check_col[f.ncheck] = c; f.check_var[f.ncheck] = atom.args[c].var; f.check_const[f.ncheck] = 0; f.ncheck++; }
      for (int c : p.bind_cols[pos]) { if (f.nbind == 8) return false; f.bind_col[f.nbind] = c; f.bind_var[f.nbind] = atom.args[c].var; f.nbind++; }
    }
    return true;
  }
  template <class Emit>
  void RunFast(const Plan& p, const std::vector<FastLevel>& L, size_t r_begin, size_t r_end, num* bind, Emit emit) {
    const Rule& rule = *p.rule;
    int natoms = L.size();
    const num* rows[8]; size_t b[8], e[8];
    num probe[4];
    auto stage = [&](int s) -> bool {
      for (int l : p.lets_after[s]) bind[rule.lets[l].first] = Eval(rule.lets[l].second, bind);
      for (int l : p.checks_after[s]) { num v = Eval(rule.lets[l].second, bind); if (std::isnan(v) || v != bind[rule.lets[l].first]) return false; }
      for (int c : p.conds_after[s]) if (!Truthy(Eval(rule.conds[c], bind))) return false;
      return true;
    };
    auto open = [&](int pos) {
      const FastLevel& f = L[pos];
      if (f.kind == 0) { b[pos] = pos == 0 ? r_begin : 0; e[pos] = pos == 0 ? r_end : f.n; return; }
      for (int i = 0; i < f.nprobe; i++) probe[i] = f.probe_var[i] < 0 ? f.probe_const[i] : bind[f.probe_var[i]];
      if (f.kind == 1) {
        i64 k = (i64)probe[0] - f.I->min_key;
        if (k < 0 || k + 1 >= (i64)f.I->offsets.size()) { b[pos] = e[pos] = 0; return; }
        b[pos] = f.I->offsets[k]; e[pos] = f.I->offsets[k + 1]; return;
      }
      uint64_t h = 1469598103934665603ULL;  // Index::Pack over the probe
      for (int i = 0; i < f.nprobe; i++) { h ^= (uint64_t)(i64)probe[i]; h *= 1099511628211ULL; h ^= h >> 29; }
      auto it = f.I->ranges.find(h);
      if (it == f.I->ranges.end()) { b[pos] = e[pos] = 0; return; }
      b[pos] = it->second.first; e[pos] = it->second.second;
    };
    bool stage_work[9];
    for (int st = 0; st <= natoms; st++) stage_work[st] = !p.lets_after[st].empty() || !p.checks_after[st].empty() || !p.conds_after[st].empty();
    if (stage_work[0] && !stage(0)) return;
    open(0);
    int pos = 0;
    const int last = natoms - 1;
    while (pos >= 0) {
      if (pos == last) {
        // The innermost level: a plain loop over its rows.
        const FastLevel& f = L[last];
        const num* row = f.base + b[last] * f.width;
        const num* end = f.base + e[last] * f.width;
        for (; row != end; row += f.width) {
          bool ok = true;
          for (int i = 0; i < f.ncheck && ok; i++) ok = row[f.check_col[i]] == (f.check_var[i] < 0 ? f.check_const[i] : bind[f.check_var[i]]);
          if (!ok) continue;
          for (int i = 0; i < f.nbind; i++) bind[f.bind_var[i]] = row[f.bind_col[i]];
          rows[last] = row;
          if (stage_work[natoms] && !stage(natoms)) continue;
          emit(rows);
        }
        pos--; continue;
      }
      if (b[pos] == e[pos]) { pos--; continue; }
      const FastLevel& f = L[pos];
      const num* row = f.base + (b[pos]++) * f.width;
      bool ok = true;
      for (int i = 0; i < f.ncheck && ok; i++) ok = row[f.check_col[i]] == (f.check_var[i] < 0 ? f.check_const[i] : bind[f.check_var[i]]);
      if (!ok) continue;
      for (int i = 0; i < f.nbind; i++) bind[f.bind_var[i]] = row[f.bind_col[i]];
      rows[pos] = row;
      if (stage_work[pos + 1] && !stage(pos + 1)) continue;
      pos++; open(pos);
    }
  }

  // Fast path for a linear monotone rule: the delta, then input atoms each
  // looked up through a CSR index on one bound column, a plain-variable
  // head and nothing to check. The generic loop computes the same thing
  // at several times the cost per matched row.
  bool FastPush(const Plan& p, State& head, std::vector<Rows>& out) {
    const Rule& rule = *p.rule;
    int natoms = rule.atoms.size();
    if (natoms < 2 || natoms > 8 || p.delta_pos != 0 || !p.preset.empty() || !rule.conds.empty() || !rule.lets.empty()) return false;
    if (!(head.dense || head.dense2 || head.packed) || head.tier == State::BLACKBOX || head.has_arg) return false;
    if (!p.const_cols[0].empty() || !p.bound_cols[0].empty() || p.makes_values) return false;
    // Where each variable is bound: (position, column).
    std::vector<std::pair<int, int>> where(rule.nvars, {-1, -1});
    for (int c : p.bind_cols[0]) where[rule.atoms[p.order[0]].args[c].var] = {0, c};
    struct Level { const Index* I; int pcol; int src_pos, src_col; };
    std::vector<Level> levels(natoms);
    for (int pos = 1; pos < natoms; pos++) {
      const Atom& atom = rule.atoms[p.order[pos]];
      if (atom.recursive || atom.left || atom.unnest || !p.idx[pos] || !p.idx[pos]->csr) return false;
      if (!p.const_cols[pos].empty() || p.bound_cols[pos].size() != 1) return false;
      int pcol = p.bound_cols[pos][0];
      auto src = where[atom.args[pcol].var];
      if (src.first < 0) return false;
      levels[pos] = {p.idx[pos], pcol, src.first, src.second};
      for (int c : p.bind_cols[pos]) where[atom.args[c].var] = {pos, c};
    }
    int width = rule.keys.size() + rule.values.size();
    int nkeys = rule.keys.size();
    // Keys are copied from the matched rows; values may be expressions,
    // evaluated over the variables the rows bind.
    std::vector<std::pair<int, int>> head_src(width, {-1, -1});
    for (int h = 0; h < width; h++) {
      const Expr& e = h < nkeys ? rule.keys[h] : rule.values[h - nkeys];
      if (e.kind == Expr::VAR && where[e.var].first >= 0) head_src[h] = where[e.var];
      else if (h < nkeys) return false;
    }
    bool computed = false;
    for (int h = nkeys; h < width; h++) computed |= head_src[h].first < 0;
    std::vector<std::vector<std::pair<int, int>>> binds(natoms);  // per atom: (var, col)
    for (int pos = 0; pos < natoms; pos++) for (int c : p.bind_cols[pos]) binds[pos].push_back({rule.atoms[p.order[pos]].args[c].var, c});
    // Group tier: the delta row carries old values; the contribution
    // computed from them is retracted.
    const State& D0 = states.at(rule.atoms[p.order[0]].rel);
    int darity = D0.arity, dnv = D0.nv;
    std::vector<int> dvars;  // variables bound to the delta's value columns
    if (head.tier == State::GROUP) for (int c = 0; c < dnv; c++) {
      const Expr& e = (int)rule.atoms[p.order[0]].args.size() > darity + c ? rule.atoms[p.order[0]].args[darity + c] : Expr();
      dvars.push_back(e.kind == Expr::VAR ? e.var : -1);
    }
    const Rows& D = *p.src[0];
    int w0 = D.width;
    size_t n0 = D.size();
    for (size_t c0 = 0; c0 < n0; c0 += CHUNK) {
      size_t c1 = std::min(n0, c0 + CHUNK);
#pragma omp parallel num_threads(threads)
      {
        Rows& O = out[omp_get_thread_num()];
        num hrow[8];
        const num* rows[8];
        size_t b[8], e[8];
        std::vector<num> bind(rule.nvars, 0);
        // A full match: head keys from the rows, values evaluated; for a
        // group head also the retraction of the old contribution.
        auto emit = [&]() {
          for (int h = 0; h < width; h++) if (head_src[h].first >= 0) hrow[h] = rows[head_src[h].first][head_src[h].second];
          if (computed) {
            for (int pos = 0; pos < natoms; pos++) for (auto& vc : binds[pos]) bind[vc.first] = rows[pos][vc.second];
            for (int h = nkeys; h < width; h++) if (head_src[h].first < 0) hrow[h] = Eval(rule.values[h - nkeys], bind.data());
          }
          const num* row0 = rows[0];
          if (p.may_null) for (int h = 0; h < nkeys; h++) if (std::isnan(hrow[h])) return;  // a null key is no fact
          bool retracted = dnv && std::isnan(row0[darity]);
          if (!retracted && head.Offer(hrow)) O.push(hrow);
          if (!dvars.empty() && !std::isnan(row0[darity + dnv])) {
            num saved[8];
            for (int c = 0; c < dnv; c++) if (dvars[c] >= 0) { saved[c] = bind[dvars[c]]; bind[dvars[c]] = row0[darity + dnv + c]; }
            for (int h = nkeys; h < width; h++) hrow[h] = -(head_src[h].first >= 0 ? bind[rule.values[h - nkeys].var] : Eval(rule.values[h - nkeys], bind.data()));
            if (head.Offer(hrow)) O.push(hrow);
            for (int c = 0; c < dnv; c++) if (dvars[c] >= 0) bind[dvars[c]] = saved[c];
          }
        };
        auto open = [&](int pos) {
          const Level& L = levels[pos];
          i64 key = (i64)rows[L.src_pos][L.src_col] - L.I->min_key;
          if (key < 0 || key + 1 >= (i64)L.I->offsets.size()) { b[pos] = e[pos] = 0; return; }
          b[pos] = L.I->offsets[key]; e[pos] = L.I->offsets[key + 1];
        };
        if (natoms == 2) {
          // One lookup: the tight loop (the general walk below costs twice as much here).
          const Level& L = levels[1];
          const Index& I = *L.I;
          const Rows& R1 = I.sorted;
          int w1 = R1.width;
#pragma omp for schedule(dynamic, 256)
          for (size_t r0 = c0; r0 < c1; r0++) {
            const num* row0 = D.data.data() + r0 * w0;
            i64 key = (i64)row0[L.src_col] - I.min_key;
            if (key < 0 || key + 1 >= (i64)I.offsets.size()) continue;
            size_t b1 = I.offsets[key], e1 = I.offsets[key + 1];
            rows[0] = row0;
            for (; b1 != e1; b1++) { rows[1] = R1.data.data() + b1 * w1; emit(); }
          }
        } else
#pragma omp for schedule(dynamic, 256)
        for (size_t r0 = c0; r0 < c1; r0++) {
          rows[0] = D.data.data() + r0 * w0;
          int pos = 1;
          open(1);
          while (pos >= 1) {
            if (b[pos] == e[pos]) { pos--; continue; }
            const Index& I = *levels[pos].I;
            rows[pos] = I.sorted.data.data() + (b[pos]++) * I.sorted.width;
            if (pos + 1 < natoms) { pos++; open(pos); continue; }
            emit();
          }
        }
      }
      head.Maintain(out[0].data);
    }
    return true;
  }

  // Push: every match is offered to the head; `out` collects the keys
  // newly queued (delta rows for the next round).
  void Push(const Rule& rule, int delta_at, std::vector<Rows>& out) {
    State& head = states.at(rule.head);
    Plan p = MakePlan(rule, delta_at, {});
    int width = rule.keys.size() + rule.values.size();
    for (auto& o : out) o.width = width;
    if (FastPush(p, head, out)) { if (trace) fprintf(stderr, "    fast push %s\n", rule.head.c_str()); return; }
    if (rule.atoms.empty()) {
      std::vector<num> bind(rule.nvars, 0), hrow(width);
      RunPlan(p, 0, 0, bind, [&](const num*) {
        for (size_t k = 0; k < rule.keys.size(); k++) hrow[k] = Eval(rule.keys[k], bind.data());
        for (size_t v = 0; v < rule.values.size(); v++) hrow[rule.keys.size() + v] = Eval(rule.values[v], bind.data());
        if (head.Offer(hrow.data())) out[0].push(hrow.data());
      });
      head.Maintain(out[0].data);
      return;
    }
    // Group tier: the delta row carries the old values of the changed
    // fact; the contribution computed from them is retracted (negated).
    std::vector<int> dvars;  // variables bound to the delta's value columns
    int darity = 0, dnv = 0;
    if (delta_at >= 0 && rule.atoms[delta_at].recursive) {
      const State& D = states.at(rule.atoms[delta_at].rel);
      darity = D.arity; dnv = D.nv;
      if (head.tier == State::GROUP) for (int c = 0; c < dnv; c++) {
        const Expr& e = (int)rule.atoms[delta_at].args.size() > darity + c ? rule.atoms[delta_at].args[darity + c] : Expr();
        dvars.push_back(e.kind == Expr::VAR ? e.var : -1);
      }
    }
    size_t n0 = p.idx[0] ? 1 : p.src[0]->size();
    int nthreads = (head.dense || head.dense2 || head.packed) && !p.makes_values ? threads : 1;
    for (size_t c0 = 0; c0 < n0; c0 += CHUNK) {
      size_t c1 = std::min(n0, c0 + CHUNK);
#pragma omp parallel num_threads(nthreads)
      {
        std::vector<num> bind(rule.nvars, 0);
        std::vector<num> hrow(width);
        Rows& O = out[omp_get_thread_num()];
        auto head_row = [&]() -> bool {
          for (size_t k = 0; k < rule.keys.size(); k++) hrow[k] = p.head_var[k] >= 0 ? bind[p.head_var[k]] : Eval(rule.keys[k], bind.data());
          for (size_t v = 0; v < rule.values.size(); v++) { size_t h = rule.keys.size() + v; hrow[h] = p.head_var[h] >= 0 ? bind[p.head_var[h]] : Eval(rule.values[v], bind.data()); }
          if (p.may_null) for (size_t k = 0; k < rule.keys.size(); k++) if (std::isnan(hrow[k])) return false;  // a null key is no fact
          return true;
        };
        // Blocks of delta rows handed out dynamically: the work per row
        // (the joins behind it) varies a lot.
#pragma omp for schedule(dynamic, 1)
        for (size_t b = c0; b < c1; b += BLOCK) RunPlan(p, b, std::min(c1, b + BLOCK), bind, [&](const num* row0) {
          bool retracted = dnv && std::isnan(row0[darity]);
          if (!retracted && head_row()) {
            if (trace && n0 < 4) fprintf(stderr, "    emit %s value %g (delta row0 %g)\n", rule.head.c_str(), width ? hrow[0] : 0, row0 ? row0[0] : -1);
            if (head.Offer(hrow.data())) O.push(hrow.data());
          }
          if (!dvars.empty() && !std::isnan(row0[darity + dnv])) {
            num saved[8];
            for (int c = 0; c < dnv; c++) if (dvars[c] >= 0) { saved[c] = bind[dvars[c]]; bind[dvars[c]] = row0[darity + dnv + c]; }
            if (head_row()) {
              for (size_t v = 0; v < rule.values.size(); v++) hrow[rule.keys.size() + v] = -hrow[rule.keys.size() + v];
              if (head.Offer(hrow.data())) O.push(hrow.data());
            }
            for (int c = 0; c < dnv; c++) if (dvars[c] >= 0) bind[dvars[c]] = saved[c];
          }
        });
      }
      head.Maintain(out[0].data);
    }
  }

  // Experiment: the delta join stores (or removes) the contribution of every
  // match and marks the key; FoldStored then folds the lists.
  void StoreAffected(const Rule& rule, int delta_at) {
    State& head = states.at(rule.head);
    Plan p = MakePlan(rule, delta_at, {});
    if (rule.atoms.empty()) {
      std::vector<num> bind(rule.nvars, 0), krow(rule.keys.size()), vals(rule.values.size());
      for (size_t k = 0; k < krow.size(); k++) krow[k] = Eval(rule.keys[k], bind.data());
      for (size_t v = 0; v < vals.size(); v++) vals[v] = Eval(rule.values[v], bind.data());
      head.StoreContribution(krow.data(), (uint64_t)(&rule - &rules[0]), vals[0], false); head.MarkDirty(krow.data());
      return;
    }
    int darity = 0, dnv = 0;
    if (delta_at >= 0 && rule.atoms[delta_at].recursive) { const State& D = states.at(rule.atoms[delta_at].rel); darity = D.arity; dnv = D.nv; }
    size_t n0 = p.idx[0] ? 1 : p.src[0]->size();
    uint64_t rule_id = (uint64_t)(&rule - &rules[0]);
#pragma omp parallel num_threads(threads)
    {
      std::vector<num> bind(rule.nvars, 0), krow(rule.keys.size());
      auto identity = [&]() {
        uint64_t h = 1469598103934665603ULL ^ rule_id;
        for (auto& atom : rule.atoms) {
          int arity = atom.recursive ? states.at(atom.rel).arity : (int)atom.args.size() - (atom.has_value ? 1 : 0);
          for (int c = 0; c < arity && c < (int)atom.args.size(); c++) {
            const Expr& e = atom.args[c];
            num x = e.kind == Expr::VAR ? bind[e.var] : e.kind == Expr::CONST ? e.value : 0;
            h ^= Bits(x); h *= 1099511628211ULL; h ^= h >> 29;
          }
        }
        return h;
      };
#pragma omp for schedule(dynamic, 1)
      for (size_t b = 0; b < n0; b += BLOCK) RunPlan(p, b, std::min(n0, b + BLOCK), bind, [&](const num* row0) {
        for (size_t k = 0; k < krow.size(); k++) krow[k] = Eval(rule.keys[k], bind.data());
        bool retracted = dnv && std::isnan(row0[darity]);
        num v = retracted ? 0 : Eval(rule.values[0], bind.data());
        head.StoreContribution(krow.data(), identity(), v, retracted);
        head.MarkDirty(krow.data());
      });
    }
  }

  // The whole predicate recomputed from its rules, as SQL would do it:
  // every rule is evaluated in full, the contributions are partitioned by
  // key hash across threads, each partition is folded per key, and the
  // result is compared with the current state: keys that moved are
  // logged, keys that received nothing are removed. No walk from the
  // changes and nothing stored between passes.
  std::map<std::string, std::vector<std::vector<Rows>>> full_buf;
  std::map<std::string, std::vector<num>> full_dvals;
  std::map<std::string, std::vector<char>> full_dseen;
  std::map<std::string, std::vector<std::vector<uint32_t>>> full_slots;
  std::set<std::string> rounds_traced;  // rules whose walk kind was already traced
  std::map<std::string, size_t> full_bodies;  // per rule: bodies in the last full pass
  std::map<std::string, size_t> full_produced;  // per state: rows the body phase produced in the last full pass
  std::vector<std::vector<num>> full_stg;    // per thread: the staging buffer of the body phase  // per state, per partition: the slot of each buffered row
  void FullRecompute(State& S, std::vector<Rows>& out) {
    // Partitions: many more than threads when the pass is big, so that the
    // slots one partition folds into span a stretch of the table that fits
    // a cache level; few when it is small, so that a short pass does not
    // pay for 256 buffers per thread.
    int T = std::max(1, threads);
    size_t& produced_before = full_produced[S.name];
    int B = produced_before > ((size_t)1 << 22) ? 256 : T;
    int w = S.arity + S.nv;
    bool collects = false;
    for (Agg a : S.aggs) collects |= Collects(a);
    // Buffers persist between passes: their capacity is the previous
    // pass's, so a pass does not page in 200 MB anew.
    std::vector<std::vector<Rows>>& buf = full_buf[S.name];
    if (full_stg.size() < (size_t)T) full_stg.resize(T);
    if (buf.size() != (size_t)T || buf[0].size() != (size_t)B) {
      buf.assign(T, std::vector<Rows>(B));
      // Staggered initial capacities, so the per-thread buffers do not land
      // on addresses congruent modulo a large power of two (cache aliasing).
      for (int t = 0; t < T; t++) for (int b = 0; b < B; b++) buf[t][b].data.reserve(4096 + 1021 * (t * B + b));
    }
    // Each buffer starts at its own offset within a page: a thread writes
    // its B buffers in step, and page-aligned starts would put all of them
    // in the same cache sets at the same time (experiment: SOCRATES_FULL_PAD).
    static const bool pad = getenv("SOCRATES_FULL_PAD") != nullptr;
    std::vector<std::vector<size_t>> skip(T, std::vector<size_t>(B, 0));
    for (int t = 0; t < T; t++) for (int b = 0; b < B; b++) {
      Rows& r = buf[t][b]; r.width = w; r.data.clear();
      if (pad) { skip[t][b] = ((t * B + b) * 37) % 61; r.data.resize(skip[t][b] * w, 0); }
    }
    // Dense keys are cut into ranges, so each partition folds into a slice
    // of a plain array; other keys are partitioned by hash.
    bool dense = S.dense && !collects;
    i64 span = dense ? (i64)S.slots.alive.size() : 0;
    // A packed state is partitioned the way its table is laid out, so the
    // fold of one partition walks one stretch of the table (the span of
    // slots it will touch fits a cache level), instead of the whole of it.
    int packed_shift = 0;
    if (S.packed) { size_t cap = S.pmap.keys.size(); while (((size_t)1 << packed_shift) < cap) packed_shift++; }
    auto bucket_of = [&](const num* key) -> int {
      if (dense) { i64 k = (i64)key[0] - S.lo; return (int)(k * B / span); }
      if (S.packed) { size_t i = PackedMap::Hash(State::PackKey(key)) & (((size_t)1 << packed_shift) - 1); return (int)(i * (size_t)B >> packed_shift); }
      uint64_t h = 0x9E3779B97F4A7C15ULL;
      for (int k = 0; k < S.arity; k++) { uint64_t bits; memcpy(&bits, &key[k], sizeof bits); h = (h ^ bits) * 0xff51afd7ed558ccdULL; h ^= h >> 32; }
      return (int)((h & 0xffffffffULL) * (uint64_t)B >> 32);
    };
    double tf0 = Now();
    // Phase 1: every body of every rule, as (key, contribution) rows.
    for (auto& rule : rules) {
      if (rule.head != S.name) continue;
      Plan p = MakePlan(rule, -1, {});
      size_t n0 = rule.atoms.empty() ? 0 : p.idx[0] ? 1 : p.src[0]->size();
      // The first atom's rows are split between threads in blocks; a rule
      // with few first rows and a wide fan-out (SG: 10K edges, 100M bodies)
      // still needs every thread, so blocks are small when rows are few.
      const size_t BLOCK = std::max<size_t>(64, n0 / ((size_t)T * 16));
      // Threads are worth it when the rule had many bodies last pass (a
      // small rule in a long iteration, as in the flow dynamics, is cheaper
      // on one thread than the parallel region costs); a rule that builds
      // values writes the arena: one thread.
      size_t& bodies_before = full_bodies[rule.head + "#" + std::to_string(&rule - &rules[0])];
      int nt = (n0 > (1 << 14) || bodies_before > (1 << 16)) && !p.makes_values ? T : 1;
      std::vector<FastLevel> levels;
      bool fast = FastLevels(p, levels);
      std::vector<int> val_var;  // per value column: the variable it copies, or -1
      for (auto& v : rule.values) val_var.push_back(v.kind == Expr::VAR ? v.var : -1);
      if (trace && rounds_traced.insert(rule.head + "#" + std::to_string(&rule - &rules[0])).second) fprintf(stderr, "    full %s: %s walk\n", rule.head.c_str(), fast ? "compact" : "general");
#pragma omp parallel num_threads(nt)
      {
        int t = omp_get_thread_num();
        std::vector<num> bind(rule.nvars, 0), row(w);
        static const bool nopush = getenv("SOCRATES_FULL_NOPUSH") != nullptr;  // experiment: join only
        auto emit = [&](const num*) {
          for (int k = 0; k < S.arity; k++) { row[k] = Eval(rule.keys[k], bind.data()); if (std::isnan(row[k])) return; }
          for (int c = 0; c < S.nv; c++) row[S.arity + c] = Eval(rule.values[c], bind.data());
          if (nopush) return;
          buf[t][bucket_of(row.data())].push(row.data());
        };
        static const int experiment = getenv("SOCRATES_FULL_EXP") ? atoi(getenv("SOCRATES_FULL_EXP")) : 0;  // 1: no bucketing, 2: no push (timing only, wrong results)
        // Rows are staged per partition and appended in blocks: one
        // vector insert per STG rows instead of one per row.
        const int STG = 128;
        std::vector<num>& stg = full_stg[t]; if (stg.size() < (size_t)B * STG * w) stg.resize((size_t)B * STG * w);
        std::vector<int> cnt(B, 0);
        auto flush = [&](int bk) { buf[t][bk].data.insert(buf[t][bk].data.end(), &stg[(size_t)bk * STG * w], &stg[((size_t)bk * STG + cnt[bk]) * w]); cnt[bk] = 0; };
        auto emit_fast = [&](const num* const*) {
          for (int k = 0; k < S.arity; k++) { row[k] = p.head_var[k] >= 0 ? bind[p.head_var[k]] : Eval(rule.keys[k], bind.data()); if (std::isnan(row[k])) return; }
          for (int c = 0; c < S.nv; c++) row[S.arity + c] = val_var[c] >= 0 ? bind[val_var[c]] : Eval(rule.values[c], bind.data());
          if (nopush || (experiment == 2 && bodies_before > 100000000)) return;  // 2: the walk alone, once the pass is big (wrong results)
          int bk = experiment == 1 ? 0 : bucket_of(row.data());
          memcpy(&stg[((size_t)bk * STG + cnt[bk]) * w], row.data(), w * sizeof(num));
          if (++cnt[bk] == STG) flush(bk);
        };
        if (nt == 1) { if (t == 0) { if (fast) RunFast(p, levels, 0, n0, bind.data(), emit_fast); else RunPlan(p, 0, n0, bind, emit); } }
        else {
#pragma omp for schedule(dynamic, 1)
          for (size_t b = 0; b < n0; b += BLOCK) { if (fast) RunFast(p, levels, b, std::min(n0, b + BLOCK), bind.data(), emit_fast); else RunPlan(p, b, std::min(n0, b + BLOCK), bind, emit); }
        }
        for (int bk = 0; bk < B; bk++) if (cnt[bk]) flush(bk);
      }
      size_t produced = 0;
      for (int t = 0; t < T; t++) for (int b = 0; b < B; b++) produced += buf[t][b].size();
      bodies_before = produced;  // all rules of the head so far: an upper bound for this rule, good enough
      produced_before = produced;
    }
    double tf1 = Now();
    // Phase 2: every key takes its slot in the state's own table, the one
    // dictionary (dense, packed or generic), and the contributions are
    // folded per slot into a shadow of the value columns. The rows of a
    // key sit in one partition, so partitions fold in parallel without
    // races. A packed table that fills up past its probe limit is grown
    // and the slots assigned again; this is rare.
    bool generic = !S.dense && !S.packed;
    std::vector<std::vector<uint32_t>>& sl = full_slots[S.name]; sl.resize(B);
    if (S.packed && S.pmap.count * 2 > S.pmap.keys.size()) S.Rehash(S.pmap.keys.size() * 2);
    for (bool spilled = true; spilled;) {
      spilled = false;
#pragma omp parallel for num_threads(generic ? 1 : T) schedule(dynamic, 1) reduction(||: spilled)
      for (int b = 0; b < B; b++) {
        std::vector<uint32_t>& L = sl[b]; L.clear();
        for (int t = 0; t < T && !spilled; t++) {
          Rows& R = buf[t][b];
          size_t n = R.size();
          for (size_t r = skip[t][b]; r < n; r++) {
            const num* row = R.row(r);
            size_t sx = S.FindSlot(row);  // a plain probe first: most keys are there from the last pass
            if (sx == ~size_t(0)) sx = S.SlotOf(row);
            if (sx == ~size_t(0)) { spilled = true; break; }
            L.push_back((uint32_t)sx);
          }
        }
      }
      if (spilled) S.Rehash(S.pmap.keys.size() * 4);  // a pass that fills the table is growing fast: fewer rounds of this
    }
    double tf1s = Now();
    size_t nslots = S.slots.alive.size();
    std::vector<num>& fv = full_dvals[S.name]; fv.resize(nslots * S.nv);
    std::vector<char>& seen = full_dseen[S.name]; seen.assign(nslots, 0);
    typedef std::unordered_map<size_t, std::vector<std::vector<num>>> Coll;  // slot -> per column, the collected values
    std::vector<Coll> coll(B);
#pragma omp parallel for num_threads(T) schedule(dynamic, 1)
    for (int b = 0; b < B; b++) {
      size_t i = 0;
      for (int t = 0; t < T; t++) {
        Rows& R = buf[t][b];
        size_t n = R.size();
        for (size_t r = skip[t][b]; r < n; r++, i++) {
          const num* v = R.row(r) + S.arity;
          size_t sx = sl[b][i];
          num* a = &fv[sx * S.nv];
          if (!seen[sx]) {
            seen[sx] = 1;
            for (int c = 0; c < S.nv; c++) a[c] = v[c];
            if (collects) { auto& C = coll[b][sx]; C.resize(S.nv); for (int c = 0; c < S.nv; c++) if (Collects(S.aggs[c])) C[c].push_back(v[c]); }
            continue;
          }
          for (int c = 0; c < S.nv; c++) switch (S.aggs[c]) {
            case SUM: if (std::isnan(a[c])) a[c] = v[c]; else if (!std::isnan(v[c])) a[c] += v[c]; break;
            case ASSIGN: a[c] = v[c]; break;
            case MIN: case MAX: {
              bool better = S.aggs[c] == MIN ? v[c] < a[c] : v[c] > a[c];
              if (!better && v[c] == a[c]) for (int d = 0; d < S.nv; d++) if (S.argof[d] == c && v[d] < a[d]) better = true;
              if (better) { a[c] = v[c]; for (int d = 0; d < S.nv; d++) if (S.argof[d] == c) a[d] = v[d]; }
              break;
            }
            case LIST: case SET: case COUNT: case ARRAYAGG: coll[b][sx][c].push_back(v[c]); break;
            default: break;
          }
        }
        R.data.clear();
      }
    }
    // Collected columns are finished serially (the arena is not shared).
    if (collects) {
      num field_arg = dict.Intern("arg"), field_value = dict.Intern("value");
      for (int b = 0; b < B; b++) for (auto& kv : coll[b]) {
        num* a = &fv[kv.first * S.nv];
        for (int c = 0; c < S.nv; c++) {
          std::vector<num>& v = kv.second[c];
          switch (S.aggs[c]) {
            case LIST: std::sort(v.begin(), v.end()); a[c] = arena.MakeArray(v.data(), v.size()); break;
            case SET: std::sort(v.begin(), v.end()); v.erase(std::unique(v.begin(), v.end()), v.end()); a[c] = arena.MakeArray(v.data(), v.size()); break;
            case COUNT: std::sort(v.begin(), v.end()); v.erase(std::unique(v.begin(), v.end()), v.end()); a[c] = v.size(); break;
            case ARRAYAGG: {
              std::vector<std::pair<num, num>> pairs;
              for (num r : v) pairs.emplace_back(arena.Field(r, field_arg), arena.Field(r, field_value));
              std::stable_sort(pairs.begin(), pairs.end(), [](const std::pair<num, num>& x, const std::pair<num, num>& y) { return x.first < y.first; });
              std::vector<num> vals; for (auto& pr : pairs) vals.push_back(pr.second);
              a[c] = arena.MakeArray(vals.data(), vals.size());
              break;
            }
            default: break;
          }
        }
      }
    }
    double tf2 = Now();
    // Phase 3: walk the slots; a slot with a fold takes it, a live slot
    // without one is removed; what moved is logged.
    for (auto& o : out) o.width = S.DeltaWidth();
    static const num present_value = 1;  // a set has no value columns: SetSlot() must not take an empty vector's null data() for a removal
    auto visit = [&](size_t sx, const num* key, Rows& O) {
      bool moved = seen[sx] ? S.SetSlot(sx, S.nv ? &fv[sx * S.nv] : &present_value)
                            : S.slots.alive[sx] == 1 && S.SetSlot(sx, nullptr);
      if (moved) { O.data.insert(O.data.end(), key, key + S.arity); for (int c = 0; c < 2 * S.nv; c++) O.data.push_back(0); }
    };
    if (generic) {
      for (auto& kv : S.table) visit(kv.second, kv.first.data(), out[0]);
    } else {
#pragma omp parallel num_threads(T)
      {
        Rows& O = out[omp_get_thread_num()];
        num key[2];
#pragma omp for schedule(static)
        for (size_t sx = 0; sx < nslots; sx++) {
          if (S.dense) key[0] = (num)(S.lo + (i64)sx);
          else { uint64_t k = S.pmap.keys[sx]; if (k == PackedMap::EMPTY || k == PackedMap::RESERVED) continue; key[0] = (num)(int32_t)(k >> 32); key[1] = (num)(int32_t)(uint32_t)k; }
          visit(sx, key, O);
        }
      }
    }
    for (auto& Oo : out) { S.next_delta.data.insert(S.next_delta.data.end(), Oo.data.begin(), Oo.data.end()); Oo.data.clear(); }
    if (trace) fprintf(stderr, "  full %s: bodies %.3f slots %.3f fold %.3f compare %.3f s\n", S.name.c_str(), tf1 - tf0, tf1s - tf1, tf2 - tf1s, Now() - tf2);
  }

  void FoldStored(State& S, std::vector<Rows>& out) {
    std::vector<std::vector<num>> dirty;
    for (auto& D : S.dirty_keys) { for (size_t i = 0; i < D.size(); i += S.arity) dirty.emplace_back(&D[i], &D[i] + S.arity); D.clear(); }
    for (auto& o : out) o.width = S.DeltaWidth();
#pragma omp parallel num_threads(threads)
    {
      Rows& O = out[omp_get_thread_num()];
#pragma omp for schedule(dynamic, 64)
      for (size_t i = 0; i < dirty.size(); i++) {
        const std::vector<num>& key = dirty[i];
        size_t s = S.FindSlot(key.data());
        num acc = 0; bool any = false;
        if (s != ~size_t(0) && s < S.contribs.size()) for (auto& c : S.contribs[s]) {
          if (!any) { acc = c.second; any = true; }
          else switch (S.aggs[0]) { case SUM: acc += c.second; break; case MIN: acc = std::min(acc, c.second); break; case MAX: acc = std::max(acc, c.second); break; default: acc = c.second; }
        }
        if (S.Set(key.data(), any ? &acc : nullptr)) { O.data.insert(O.data.end(), key.begin(), key.end()); for (int c = 0; c < 2 * S.nv; c++) O.data.push_back(0); }
        if (s != ~size_t(0)) S.slots.dirty[s] = 0;
      }
    }
    for (auto& O : out) { S.next_delta.data.insert(S.next_delta.data.end(), O.data.begin(), O.data.end()); O.data.clear(); }
  }

  // Affected keys: every match marks its head key dirty. A changed value
  // may have made a different head key before: the delta is also matched
  // with its old values (a key computed from the value is retracted).
  void MarkAffected(const Rule& rule, int delta_at) {
    MarkAffectedWith(rule, delta_at);
    if (delta_at < 0 || !rule.atoms[delta_at].has_value) return;
    State& D = states.at(rule.atoms[delta_at].rel);
    if (!D.nv) return;
    Rows old; old.width = D.delta.width;
    for (size_t r = 0; r < D.delta.size(); r++) {
      const num* row = D.delta.row(r);
      if (std::isnan(row[D.arity + D.nv])) continue;  // the fact was new
      old.push(row);
      num* o = old.row(old.size() - 1);
      for (int c = 0; c < D.nv; c++) o[D.arity + c] = row[D.arity + D.nv + c];
    }
    if (!old.size()) return;
    if (trace) fprintf(stderr, "  %s <- %s: marking with %zu old rows\n", rule.head.c_str(), D.name.c_str(), old.size());
    std::swap(D.delta, old);
    MarkAffectedWith(rule, delta_at);
    std::swap(D.delta, old);
  }

  void MarkAffectedWith(const Rule& rule, int delta_at) {
    State& head = states.at(rule.head);
    Plan p = MakePlan(rule, delta_at, {}, true);
    if (rule.atoms.empty()) {  // a fact: its key
      std::vector<num> bind(rule.nvars, 0), krow(rule.keys.size());
      for (size_t k = 0; k < rule.keys.size(); k++) krow[k] = Eval(rule.keys[k], bind.data());
      head.MarkDirty(krow.data());
      return;
    }
    size_t n0 = p.idx[0] ? 1 : p.src[0]->size();
#pragma omp parallel num_threads(p.makes_values ? 1 : threads)
    {
      std::vector<num> bind(rule.nvars, 0);
      std::vector<num> krow(rule.keys.size());
#pragma omp for schedule(dynamic, 1)
      for (size_t b = 0; b < n0; b += BLOCK) RunPlan(p, b, std::min(n0, b + BLOCK), bind, [&](const num*) {
        bool null_key = false;
        for (size_t k = 0; k < rule.keys.size(); k++) { krow[k] = Eval(rule.keys[k], bind.data()); null_key |= std::isnan(krow[k]); }
        if (!null_key) head.MarkDirty(krow.data());  // a null key is no fact
      });
    }
  }

  // Black-box recomputation of a state's dirty keys: every rule of the
  // head is evaluated with the key bound; the contributions are folded
  // column by column.
  void Pull(State& S, std::vector<Rows>& out) {
    std::vector<std::vector<num>> dirty;
    for (auto& D : S.dirty_keys) { for (size_t i = 0; i < D.size(); i += S.arity) dirty.emplace_back(&D[i], &D[i] + S.arity); D.clear(); }
    std::set<std::vector<num>> overflow;
    for (auto& D : S.dirty_overflow) { for (size_t i = 0; i < D.size(); i += S.arity) overflow.insert(std::vector<num>(&D[i], &D[i] + S.arity)); D.clear(); }
    for (auto& k : overflow) { size_t s = S.FindSlot(k.data()); if (s == ~size_t(0) || !S.slots.dirty[s]) dirty.push_back(k); }
    if (S.arity == 0 && S.dirty0) { S.dirty0 = 0; dirty.emplace_back(); }
    if (trace) fprintf(stderr, "  %s: %zu dirty keys\n", S.name.c_str(), dirty.size());
    if (dirty.empty()) return;
    // A rule whose head keys are variables (or constants) is evaluated
    // with the key bound; one with a computed key is evaluated in full
    // and its contributions bucketed by key.
    struct Pending { const Rule* rule; Plan plan; std::vector<int> key_vars; };
    std::vector<Pending> plans;  // built serially: indexes are shared
    std::unordered_map<std::vector<num>, std::vector<num>, KeyHash> computed;  // key -> contributions
    for (auto& rule : rules) {
      if (rule.head != S.name) continue;
      bool plain = true;
      for (auto& k : rule.keys) plain &= k.kind != Expr::OP;
      if (plain) {
        std::vector<int> key_vars;
        for (auto& k : rule.keys) key_vars.push_back(k.kind == Expr::VAR ? k.var : -1);
        std::vector<int> preset; for (int v : key_vars) if (v >= 0) preset.push_back(v);
        plans.push_back({&rule, MakePlan(rule, -1, preset), key_vars});
        continue;
      }
      Plan p = MakePlan(rule, -1, {});
      std::vector<num> bind(rule.nvars, 0), key(S.arity);
      RunPlan(p, 0, rule.atoms.empty() ? 0 : p.idx[0] ? 1 : p.src[0]->size(), bind, [&](const num*) {
        bool null_key = false;
        for (int k = 0; k < S.arity; k++) { key[k] = Eval(rule.keys[k], bind.data()); null_key |= std::isnan(key[k]); }
        if (null_key) return;  // a null key is no fact
        std::vector<num>& C = computed[key];
        for (int c = 0; c < S.nv; c++) C.push_back(Eval(rule.values[c], bind.data()));
      });
    }
    for (auto& o : out) o.width = S.DeltaWidth();
    if (S.packed) {
      size_t need = S.pmap.count + dirty.size();
      size_t cap = S.pmap.keys.size();
      while (need * 2 > cap) cap <<= 1;
      if (cap != S.pmap.keys.size()) S.Rehash(cap);
    }
    bool generic = !S.dense && !S.packed;
    bool collects = false, makes = false;
    for (Agg a : S.aggs) collects |= Collects(a);
    for (auto& pd : plans) makes |= pd.plan.makes_values;
    num field_arg = dict.Intern("arg"), field_value = dict.Intern("value");
#pragma omp parallel num_threads(generic || collects || makes ? 1 : threads)
    {
      Rows& O = out[omp_get_thread_num()];
      std::vector<num> acc(S.nv), contrib(S.nv);
      std::vector<std::vector<num>> collected(S.nv);  // per collecting column
      std::vector<std::vector<num>> binds;
      for (auto& pd : plans) binds.emplace_back(pd.rule->nvars, 0);
      bool any = false;
      auto fold = [&](const num* v) {
        if (!any) { for (int c = 0; c < S.nv; c++) { acc[c] = v[c]; if (Collects(S.aggs[c])) collected[c].push_back(v[c]); } any = true; return; }
        for (int c = 0; c < S.nv; c++) {
          switch (S.aggs[c]) {
            case LIST: case SET: case COUNT: case ARRAYAGG: collected[c].push_back(v[c]); break;
            case SUM: if (std::isnan(acc[c])) acc[c] = v[c]; else if (!std::isnan(v[c])) acc[c] += v[c]; break;
            case ASSIGN: acc[c] = v[c]; break;
            case MIN: case MAX: {
              bool better = S.aggs[c] == MIN ? v[c] < acc[c] : v[c] > acc[c];
              if (!better && v[c] == acc[c]) for (int d = 0; d < S.nv; d++) if (S.argof[d] == c && v[d] < acc[d]) better = true;
              if (better) {
                acc[c] = v[c];
                for (int d = 0; d < S.nv; d++) if (S.argof[d] == c) acc[d] = v[d];
              }
              break;
            }
            default: break;
          }
        }
      };
#pragma omp for schedule(dynamic, 64)
      for (size_t i = 0; i < dirty.size(); i++) {
        const std::vector<num>& key = dirty[i];
        any = false;
        for (size_t pi = 0; pi < plans.size(); pi++) {
          Pending& pd = plans[pi];
          const Rule& rule = *pd.rule;
          std::vector<num>& bind = binds[pi];
          bool match = true;
          for (size_t k = 0; k < pd.key_vars.size(); k++) {
            if (pd.key_vars[k] >= 0) bind[pd.key_vars[k]] = key[k];
            else match &= rule.keys[k].value == key[k];
          }
          if (!match) continue;
          RunPlan(pd.plan, 0, rule.atoms.empty() ? 0 : pd.plan.src[0]->size(), bind, [&](const num*) {
            for (int c = 0; c < S.nv; c++) contrib[c] = Eval(rule.values[c], bind.data());
            fold(contrib.data());
          });
        }
        if (!computed.empty()) {
          auto it = computed.find(key);
          if (it != computed.end()) for (size_t j = 0; j < it->second.size(); j += S.nv) fold(&it->second[j]);
        }
        // Collected columns: a sorted list, a set, a count, or the values
        // of {arg, value} pairs in the order of arg.
        if (any && collects) for (int c = 0; c < S.nv; c++) {
          std::vector<num>& v = collected[c];
          switch (S.aggs[c]) {
            case LIST: std::sort(v.begin(), v.end()); acc[c] = arena.MakeArray(v.data(), v.size()); break;
            case SET: std::sort(v.begin(), v.end()); v.erase(std::unique(v.begin(), v.end()), v.end()); acc[c] = arena.MakeArray(v.data(), v.size()); break;
            case COUNT: std::sort(v.begin(), v.end()); v.erase(std::unique(v.begin(), v.end()), v.end()); acc[c] = v.size(); break;
            case ARRAYAGG: {
              std::vector<std::pair<num, num>> pairs;
              for (num r : v) pairs.emplace_back(arena.Field(r, field_arg), arena.Field(r, field_value));
              std::stable_sort(pairs.begin(), pairs.end(), [](const std::pair<num, num>& a, const std::pair<num, num>& b) { return a.first < b.first; });
              std::vector<num> vals; for (auto& pr : pairs) vals.push_back(pr.second);
              acc[c] = arena.MakeArray(vals.data(), vals.size());
              break;
            }
            default: break;
          }
          v.clear();
        }
        bool changed = S.Set(key.data(), any ? acc.data() : nullptr);
        if (trace && dirty.size() <= 4) fprintf(stderr, "    %s key %g: %s -> %s\n", S.name.c_str(), key.empty() ? 0.0 : key[0], any ? "derived" : "no derivation", changed ? "changed" : "same");
        if (changed) {
          O.data.insert(O.data.end(), key.begin(), key.end());
          for (int c = 0; c < 2 * S.nv; c++) O.data.push_back(0);
        }
        if (!generic) { size_t s = S.FindSlot(key.data()); if (s != ~size_t(0)) S.slots.dirty[s] = 0; }
      }
    }
    for (auto& O : out) { S.next_delta.data.insert(S.next_delta.data.end(), O.data.begin(), O.data.end()); O.data.clear(); }
  }

  // Moves pushed keys into the next delta.
  void Collect(State& S, std::vector<Rows>& out) {
    for (auto& O : out) {
      size_t n = O.size();
      for (size_t r = 0; r < n; r++) {
        const num* row = O.row(r);
        S.next_delta.data.insert(S.next_delta.data.end(), row, row + S.arity);
        for (int c = 0; c < 2 * S.nv; c++) S.next_delta.data.push_back(0);
      }
      O.data.clear();
    }
  }

  // ------------------------------------------------------ semigroup tier
  // Folds a multiset of contributions (nv values each) into acc. Returns
  // false when the multiset is empty.
  bool FoldBag(const State& S, const std::vector<num>& bag, std::vector<num>& acc) {
    int nv = S.nv;
    size_t n = bag.size() / nv;
    if (n == 0) return false;
    acc.assign(bag.begin(), bag.begin() + nv);
    bool collects = false;
    for (Agg a : S.aggs) collects |= Collects(a);
    for (size_t i = 1; i < n; i++) {
      const num* v = &bag[i * nv];
      for (int c = 0; c < nv; c++) switch (S.aggs[c]) {
        case SUM: if (std::isnan(acc[c])) acc[c] = v[c]; else if (!std::isnan(v[c])) acc[c] += v[c]; break;
        case ASSIGN: acc[c] = v[c]; break;
        case MIN: case MAX: {
          bool better = S.aggs[c] == MIN ? v[c] < acc[c] : v[c] > acc[c];
          if (!better && v[c] == acc[c]) for (int d = 0; d < nv; d++) if (S.argof[d] == c && v[d] < acc[d]) better = true;
          if (better) { acc[c] = v[c]; for (int d = 0; d < nv; d++) if (S.argof[d] == c) acc[d] = v[d]; }
          break;
        }
        default: break;
      }
    }
    if (collects) {
      num field_arg = dict.Intern("arg"), field_value = dict.Intern("value");
      for (int c = 0; c < nv; c++) {
        if (!Collects(S.aggs[c])) continue;
        std::vector<num> v; for (size_t i = 0; i < n; i++) v.push_back(bag[i * nv + c]);
        switch (S.aggs[c]) {
          case LIST: std::sort(v.begin(), v.end()); acc[c] = arena.MakeArray(v.data(), v.size()); break;
          case SET: std::sort(v.begin(), v.end()); v.erase(std::unique(v.begin(), v.end()), v.end()); acc[c] = arena.MakeArray(v.data(), v.size()); break;
          case COUNT: std::sort(v.begin(), v.end()); v.erase(std::unique(v.begin(), v.end()), v.end()); acc[c] = v.size(); break;
          case ARRAYAGG: {
            std::vector<std::pair<num, num>> pairs;
            for (num r : v) pairs.emplace_back(arena.Field(r, field_arg), arena.Field(r, field_value));
            std::stable_sort(pairs.begin(), pairs.end(), [](const std::pair<num, num>& x, const std::pair<num, num>& y) { return x.first < y.first; });
            std::vector<num> vals; for (auto& pr : pairs) vals.push_back(pr.second);
            acc[c] = arena.MakeArray(vals.data(), vals.size());
            break;
          }
          default: break;
        }
      }
    }
    return true;
  }

  // The delta join of a semigroup head: every body completed from a
  // changed fact yields (key, +1, contribution) with the new binding and
  // (key, -1, contribution) with the old one, each only if the body's
  // conditions hold under that binding. delta_at < 0: a full evaluation
  // (the first pass of a rule without a regular changing atom).
  void PushSemi(const Rule& rule, int delta_at, std::vector<Rows>& out) {
    State& head = states.at(rule.head);
    plan_point_lookups = true;
    Plan p = MakePlan(rule, delta_at, {}, true);  // conditions on changing values are deferred to here
    plan_point_lookups = false;
    int nkeys = rule.keys.size(), nv = rule.values.size();
    int width = nkeys + 1 + nv;
    for (auto& o : out) o.width = width;
    // Which lets are equalities (their variable is bound by an atom).
    std::vector<char> is_def(rule.lets.size(), 0);
    for (auto& st : p.lets_after) for (int l : st) is_def[l] = 1;
    auto holds = [&](std::vector<num>& bind) -> bool {
      for (size_t l = 0; l < rule.lets.size(); l++) {
        num v = Eval(rule.lets[l].second, bind.data());
        if (is_def[l]) bind[rule.lets[l].first] = v;
        else if (std::isnan(v) || v != bind[rule.lets[l].first]) return false;
      }
      for (auto& c : rule.conds) if (!Truthy(Eval(c, bind.data()))) return false;
      return true;
    };
    // The two sides of a change: the body completed with the new values of
    // the changed fact (+1) and, separately, with its old values (-1); each
    // side is a whole run of the plan, so lookups and lists that depend on
    // the value are taken as they were. A regular fact that is absent on a
    // side has no body there; a left atom's absence is the value null.
    Rows side_rows[2];
    const Rows* delta_src = nullptr;
    if (delta_at >= 0 && rule.atoms[delta_at].recursive) {
      const State& D = states.at(rule.atoms[delta_at].rel);
      int da = D.arity, dn = D.nv;
      bool left = rule.atoms[delta_at].left;
      const Rows& delta = D.delta;
      delta_src = p.src[0];
      for (int side = 0; side < 2; side++) {
        Rows& R = side_rows[side]; R.width = delta.width;
        for (size_t r = 0; r < delta.size(); r++) {
          const num* row = delta.row(r);
          const num* vals = side == 0 ? row + da : row + da + dn;
          if (dn && !left && std::isnan(vals[0])) continue;  // no fact on this side
          if (side == 1 && dn == 0) continue;               // a set's row only appears
          R.data.insert(R.data.end(), row, row + da);
          R.data.insert(R.data.end(), vals, vals + dn);
          R.data.insert(R.data.end(), side == 0 ? row + da + dn : row + da, side == 0 ? row + da + dn + dn : row + da + dn);
        }
      }
    }
    for (int side = 0; side < (delta_src ? 2 : 1); side++) {
      if (delta_src) { p.src[0] = &side_rows[side]; if (side_rows[side].size() == 0) continue; }
      num sign = side == 0 ? 1 : -1;
      size_t n0 = rule.atoms.empty() ? 0 : p.point[0] || p.idx[0] ? 1 : p.src[0]->size();
      // A few changed rows are not worth a parallel region.
      int nthreads = p.makes_values || rule.atoms.empty() || n0 < 2048 ? 1 : threads;
#pragma omp parallel num_threads(nthreads)
      {
        std::vector<num> bind(rule.nvars, 0), row(width);
        Rows& O = out[omp_get_thread_num()];
        auto body = [&](const num*) {
          if (!holds(bind)) return;
          for (int k = 0; k < nkeys; k++) { row[k] = Eval(rule.keys[k], bind.data()); if (std::isnan(row[k])) return; }
          row[nkeys] = sign;
          for (int v = 0; v < nv; v++) row[nkeys + 1 + v] = Eval(rule.values[v], bind.data());
          O.push(row.data());
        };
        if (rule.atoms.empty()) { if (omp_get_thread_num() == 0) RunPlan(p, 0, 0, bind, body); }
        else {
#pragma omp for schedule(dynamic, 1)
          for (size_t b = 0; b < n0; b += BLOCK) RunPlan(p, b, std::min(n0, b + BLOCK), bind, body);
        }
      }
    }
    if (delta_src) p.src[0] = delta_src;
    (void)head;
  }

  // The state as it was before the log rows [from, to): the current rows
  // with those changes reverted (a key whose old value is absent removed).
  Rows Before(State& B, size_t from, size_t to) {
    Rows cur = B.Materialize();
    int w = cur.width, a = B.arity, nv = B.nv;
    std::unordered_map<std::vector<num>, std::vector<num>, KeyHash> rows;
    for (size_t r = 0; r < cur.size(); r++) rows[std::vector<num>(cur.row(r), cur.row(r) + a)] = std::vector<num>(cur.row(r), cur.row(r) + w);
    for (size_t r = from; r < to; r++) {
      const num* row = B.log.row(r);
      std::vector<num> key(row, row + a);
      if (nv == 0 || std::isnan(row[a + nv])) rows.erase(key);  // appeared: was not there
      else { std::vector<num> old(row, row + a); old.insert(old.end(), row + a + nv, row + a + 2 * nv); rows[key] = old; }
    }
    Rows R; R.width = w;
    for (auto& kv : rows) R.data.insert(R.data.end(), kv.second.begin(), kv.second.end());
    return R;
  }

  // The materialized state with the overlay applied (for atoms that must be scanned).
  Rows BeforeFromOverlay(const State& B) {
    Rows cur = const_cast<State&>(B).Materialize();
    auto ov = before_overlay.find(B.name);
    if (ov == before_overlay.end()) return cur;
    int w = cur.width, a = B.arity;
    Rows R; R.width = w;
    for (size_t r = 0; r < cur.size(); r++) {
      std::vector<num> key(cur.row(r), cur.row(r) + a);
      auto it = ov->second.find(key);
      if (it == ov->second.end()) R.push(cur.row(r));
      else if (!it->second.empty()) R.push(it->second.data());
    }
    for (auto& kv : ov->second) {
      if (kv.second.empty()) continue;
      size_t slot = B.FindSlot(kv.first.data());
      if (slot == ~size_t(0) || B.slots.alive[slot] != 1) R.push(kv.second.data());  // gone now, was there before
    }
    return R;
  }

  // Applies the (key, sign, contribution) rows to the bags, folds the
  // touched keys again, and logs the ones that moved. Serial.
  void ApplySemi(State& S, std::vector<Rows>& out) {
    int nkeys = S.arity, nv = S.nv;
    bool collects = false;
    for (Agg a : S.aggs) collects |= Collects(a);
    // Slots are found serially (the generic table grows); the rest is per slot.
    std::vector<std::pair<size_t, const num*>> work;
    size_t nslots = 0;
    for (auto& O : out) {
      size_t n = O.size();
      for (size_t r = 0; r < n; r++) {
        const num* row = O.row(r);
        size_t slot = S.SlotOf(row);
        if (slot == ~size_t(0)) Fail("no slot for a key of " + S.name);
        work.emplace_back(slot, row);
        nslots = std::max(nslots, slot + 1);
      }
    }
    if (S.exists) { if (S.refs.size() < nslots) S.refs.resize(nslots, 0); }
    else if (S.bag.size() < nslots) S.bag.resize(nslots);
    int T = collects || work.size() < 4096 ? 1 : std::max(1, threads);
    std::vector<std::vector<num>> logs(T);
    static const num present_value = 1;
#pragma omp parallel num_threads(T)
    {
      int t = omp_get_thread_num();
      std::vector<size_t> touched;
      std::unordered_map<size_t, std::vector<const num*>> removals;  // slot -> withdrawn values
      // The rows of a visit are one multiset difference: all additions
      // first, then all removals, so that a contribution added by a later
      // atom's change is there when an earlier atom's change removes it.
      for (int phase = 0; phase < 2; phase++) for (auto& w : work) {
        size_t slot = w.first;
        if ((int)(slot % T) != t) continue;
        const num* row = w.second;
        if ((row[nkeys] > 0) != (phase == 0)) continue;
        if (S.exists) S.refs[slot] += row[nkeys] > 0 ? 1 : -1;
        else {
          std::vector<num>& bag = S.bag[slot];
          const num* v = row + nkeys + 1;
          if (row[nkeys] > 0) bag.insert(bag.end(), v, v + nv);
          else removals[slot].push_back(v);
        }
        touched.push_back(slot);
      }
      // Withdrawals: one contribution equal to each withdrawn value leaves
      // the bag; for a commutative fold any equal one will do. A few are
      // found by scanning; many are counted and the bag is filtered once,
      // so that a key whose whole bag moves on is not quadratic.
      for (auto& rs : removals) {
        std::vector<num>& bag = S.bag[rs.first];
        size_t missing = 0;
        if (rs.second.size() <= 16) {
          for (const num* v : rs.second) {
            bool found = false;
            for (size_t at = bag.size(); at >= (size_t)nv && !found; at -= nv) {
              size_t i = at - nv;
              if (SameValues(&bag[i], v, nv)) { bag.erase(bag.begin() + i, bag.begin() + i + nv); found = true; }
              if (i == 0) break;
            }
            missing += !found;
          }
        } else {
          std::unordered_map<std::vector<num>, size_t, KeyHash, NanEqual> count;
          std::vector<num> val(nv);
          for (const num* v : rs.second) { val.assign(v, v + nv); count[val]++; }
          std::vector<num> kept;
          kept.reserve(bag.size());
          for (size_t i = 0; i + nv <= bag.size(); i += nv) {
            val.assign(&bag[i], &bag[i] + nv);
            auto it = count.find(val);
            if (it != count.end() && it->second > 0) { it->second--; continue; }
            kept.insert(kept.end(), &bag[i], &bag[i] + nv);
          }
          bag.swap(kept);
          for (auto& kv : count) missing += kv.second;
        }
        if (missing && trace) fprintf(stderr, "  %s: %zu withdrawn contributions were not in the bag\n", S.name.c_str(), missing);
      }
      std::sort(touched.begin(), touched.end());
      touched.erase(std::unique(touched.begin(), touched.end()), touched.end());
      std::vector<num> acc(nv), key(nkeys);
      std::unordered_map<size_t, const num*> key_of;
      for (auto& w : work) if ((int)(w.first % T) == t) key_of.emplace(w.first, w.second);
      for (size_t slot : touched) {
        const num* k = key_of[slot];
        bool changed;
        if (S.exists) changed = S.Set(k, S.refs[slot] > 0 ? &present_value : nullptr);
        else changed = S.Set(k, FoldBag(S, S.bag[slot], acc) ? acc.data() : nullptr);
        if (changed) { logs[t].insert(logs[t].end(), k, k + nkeys); for (int c = 0; c < 2 * nv; c++) logs[t].push_back(0); }
      }
    }
    for (auto& L : logs) S.next_delta.data.insert(S.next_delta.data.end(), L.begin(), L.end());
    for (auto& O : out) O.data.clear();
    for (auto& o : out) o.width = S.DeltaWidth();
  }

  // ------------------------------------------ edge-stored semigroup (experiment)
  // SOCRATES_SEMI=edge: the contributions of a body live on its edge, named
  // by the keys of the changing atoms and the head key. A change of a
  // source replaces every edge from it: the old bags are dropped, the new
  // ones computed from the new values and written over. Nothing is
  // recomputed backwards and nothing is subtracted; the heads whose edges
  // changed are folded again from their in-edges.
  static constexpr num ANY_KEY = -1e300;  // an unbound key column in an edge's name
  // Edges live in partitions by the residue of the head slot. A partition
  // owns its edge numbers, its name table (open addressing over integer
  // names), its in-edges per head slot and its out-edges per source slot,
  // so the partitions work in parallel without sharing anything.
  struct EdgePart {
    int width = 0;                        // ints per name: rule, source slots, head slot
    std::vector<int64_t> names;           // per edge: its name (width ints)
    std::vector<int> table;               // open addressing: edge number or -1; a dead edge's entry is a tombstone
    size_t mask = 0, count = 0, used = 0;  // live edges; table entries taken (live or tombstone)
    std::vector<std::vector<num>> bag;    // per edge: contributions
    std::vector<size_t> head;             // per edge: head slot
    std::vector<char> dead;
    std::vector<int> gen;
    std::vector<int> free_list;
    std::vector<std::vector<std::pair<int, int>>> in_edges;   // by head slot / T
    std::vector<std::vector<num>> head_key;                   // by head slot / T
    std::map<std::pair<int, int>, std::vector<std::vector<std::pair<int, int>>>> out_edges;  // (rule, atom) -> source slot -> edges here
    std::map<std::pair<int, int>, std::unordered_map<std::vector<num>, std::vector<std::pair<int, int>>, KeyHash>> out_any;  // wildcard names
    static uint64_t Hash(const int64_t* n, int w) { uint64_t h = 1469598103934665603ULL; for (int i = 0; i < w; i++) { h ^= (uint64_t)n[i]; h *= 1099511628211ULL; h ^= h >> 29; } return h; }
    void Grow() {
      size_t cap = table.empty() ? 1024 : (count * 4 > table.size() ? table.size() * 2 : table.size());  // rehash drops the tombstones
      std::vector<int> t(cap, -1); mask = cap - 1;
      for (int e : table) if (e >= 0 && !dead[e]) { size_t i = Hash(&names[(size_t)e * width], width) & mask; while (t[i] >= 0) i = (i + 1) & mask; t[i] = e; }
      table.swap(t); used = count;
    }
    // Finds the live edge with this name, or -1.
    int Find(const int64_t* n) const {
      if (table.empty()) return -1;
      size_t i = Hash(n, width) & mask;
      for (;;) { int e = table[i]; if (e < 0) return -1; if (!dead[e] && memcmp(&names[(size_t)e * width], n, width * sizeof(int64_t)) == 0) return e; i = (i + 1) & mask; }
    }
    int Add(const int64_t* n) {
      if ((used + 1) * 2 > table.size()) Grow();
      int e;
      if (!free_list.empty()) { e = free_list.back(); free_list.pop_back(); gen[e]++; dead[e] = 0; bag[e].clear(); }
      else { e = bag.size(); bag.emplace_back(); head.push_back(0); dead.push_back(0); gen.push_back(0); names.resize((size_t)(e + 1) * width); }
      memcpy(&names[(size_t)e * width], n, width * sizeof(int64_t));
      size_t i = Hash(n, width) & mask;
      while (table[i] >= 0 && !dead[table[i]]) i = (i + 1) & mask;
      if (table[i] < 0) used++;  // an empty entry taken; a tombstone reused counts already
      table[i] = e; count++;
      return e;
    }
    void Kill(int e) { dead[e] = 1; bag[e].clear(); free_list.push_back(e); count--; }  // its table slot is skipped by Find and reused by Add
  };
  struct EdgeStore { int T = 0; std::vector<EdgePart> part; std::vector<std::vector<size_t>> touched; std::vector<std::unordered_map<size_t, std::vector<num>>> diff; };  // diff: per partition, head slot -> running sum of changes (sum heads)
  std::map<std::string, EdgeStore> edge_store;
  bool semi_edge = getenv("SOCRATES_SEMI") && !strcmp(getenv("SOCRATES_SEMI"), "edge");

  void PushSemiEdge(const Rule& rule, int rule_index, int delta_at, std::vector<Rows>& out) {
    State& head = states.at(rule.head);
    EdgeStore& E = edge_store[head.name];
    bool collects = false; for (Agg a : head.aggs) collects |= Collects(a);
    if (E.T == 0) { E.T = collects ? 1 : std::max(1, threads); E.part.resize(E.T); E.touched.resize(E.T); E.diff.resize(E.T); }
    int T = E.T;
    // A head whose columns are all sums keeps its value by differences: the
    // stored edge gives the old contribution, so nothing is folded again.
    bool by_diff = head.nv > 0 && getenv("SOCRATES_EDGE_DIFF"); for (Agg a : head.aggs) by_diff &= a == SUM;
    plan_point_lookups = true;
    Plan p = MakePlan(rule, delta_at, {}, true);
    plan_point_lookups = false;
    int nkeys = rule.keys.size(), nv = rule.values.size();
    std::vector<int> rec_atoms;
    for (size_t a = 0; a < rule.atoms.size(); a++) if (rule.atoms[a].recursive) rec_atoms.push_back(a);
    int nsrc = rec_atoms.size();
    // The name width is the same for every rule of the head: rule, as many
    // source slots as the widest rule has (padded with -2), head slot.
    int nw = 2;
    for (auto& r2 : rules) if (r2.head == head.name) { int n = 0; for (auto& a : r2.atoms) n += a.recursive; nw = std::max(nw, 2 + n); }
    for (auto& P : E.part) if (P.width == 0) P.width = nw;
    // Row layout: head key, then per source atom its key, then the values.
    int kw = nkeys; for (int a : rec_atoms) kw += states.at(rule.atoms[a].rel).arity;
    int width = kw + nv;
    for (auto& o : out) o.width = width;
    std::vector<char> is_def(rule.lets.size(), 0);
    for (auto& st : p.lets_after) for (int l : st) is_def[l] = 1;
    auto holds = [&](std::vector<num>& bind) -> bool {
      for (size_t l = 0; l < rule.lets.size(); l++) {
        num v = Eval(rule.lets[l].second, bind.data());
        if (is_def[l]) bind[rule.lets[l].first] = v;
        else if (std::isnan(v) || v != bind[rule.lets[l].first]) return false;
      }
      for (auto& c : rule.conds) if (!Truthy(Eval(c, bind.data()))) return false;
      return true;
    };
    // 1. Drop every edge from the changed keys, in parallel over partitions.
    Rows new_rows;
    const Rows* delta_src = nullptr;
    size_t removed = 0;
    if (delta_at >= 0 && rule.atoms[delta_at].recursive) {
      const State& D = states.at(rule.atoms[delta_at].rel);
      int da = D.arity, dn = D.nv;
      bool left = rule.atoms[delta_at].left;
      const Rows& delta = D.delta;
      delta_src = p.src[0];
      new_rows.width = delta.width;
      bool wild = false; for (int c = 0; c < da; c++) wild |= rule.atoms[delta_at].args[c].kind == Expr::OP;
      std::vector<size_t> dslot(delta.size(), ~size_t(0));
      for (size_t r = 0; r < delta.size(); r++) {
        const num* row = delta.row(r);
        if (!wild) dslot[r] = D.FindSlot(row);
        if (dn && !left && std::isnan(row[da])) continue;
        new_rows.data.insert(new_rows.data.end(), row, row + delta.width);
      }
      int nt_r = delta.size() < 2048 ? 1 : T;  // a few changed rows: one thread walks the partitions
#pragma omp parallel for num_threads(nt_r) reduction(+ : removed) schedule(static)
      for (int t = 0; t < T; t++) {
        EdgePart& P = E.part[t];
        auto& touched = E.touched[t];
        auto oi = P.out_edges.find({rule_index, delta_at});
        auto oa = P.out_any.find({rule_index, delta_at});
        std::vector<num> key(da);
        for (size_t r = 0; r < delta.size(); r++) {
          std::vector<std::pair<int, int>>* list = nullptr;
          if (wild) { if (oa == P.out_any.end()) continue; const num* row = delta.row(r); for (int c = 0; c < da; c++) key[c] = rule.atoms[delta_at].args[c].kind == Expr::OP ? ANY_KEY : row[c]; auto it = oa->second.find(key); if (it != oa->second.end()) list = &it->second; }
          else { if (oi == P.out_edges.end() || dslot[r] == ~size_t(0) || dslot[r] >= oi->second.size()) continue; list = &oi->second[dslot[r]]; }
          if (!list) continue;
          for (auto& eg : *list) {
            int e = eg.first; if (P.dead[e] || P.gen[e] != eg.second) continue;
            touched.push_back(P.head[e]);
            if (by_diff) { std::vector<num>& d = E.diff[t][P.head[e]]; if (d.empty()) d.assign(nv, 0); for (size_t i = 0; i < P.bag[e].size(); i += nv) for (int c = 0; c < nv; c++) if (!std::isnan(P.bag[e][i + c])) d[c] -= P.bag[e][i + c]; }
            P.Kill(e); removed++;
          }
          list->clear();
        }
      }
      p.src[0] = &new_rows;
    }
    // 2. The bodies from the new values.
    size_t n0 = rule.atoms.empty() ? 0 : p.point[0] || p.idx[0] ? 1 : p.src[0]->size();
    if (delta_src && n0 == 0) { p.src[0] = delta_src; if (trace) fprintf(stderr, "    edges of %s rule %d from atom %d: %zu removed, 0 bodies\n", head.name.c_str(), rule_index, delta_at, removed); return; }
    int nthreads = p.makes_values || rule.atoms.empty() || n0 < 2048 ? 1 : threads;
#pragma omp parallel num_threads(nthreads)
    {
      std::vector<num> bind(rule.nvars, 0), row(width);
      Rows& O = out[omp_get_thread_num()];
      auto body = [&](const num*) {
        if (!holds(bind)) return;
        int w = 0;
        for (int k = 0; k < nkeys; k++) { row[w] = Eval(rule.keys[k], bind.data()); if (std::isnan(row[w])) return; w++; }
        for (int a : rec_atoms) { const Atom& atom = rule.atoms[a]; int ar = states.at(atom.rel).arity; for (int c = 0; c < ar; c++) { const Expr& e = atom.args[c]; row[w++] = e.kind == Expr::CONST ? e.value : e.kind == Expr::VAR ? bind[e.var] : ANY_KEY; } }
        for (int v = 0; v < nv; v++) row[w++] = Eval(rule.values[v], bind.data());
        O.push(row.data());
      };
      if (rule.atoms.empty()) { if (omp_get_thread_num() == 0) RunPlan(p, 0, 0, bind, body); }
      else {
#pragma omp for schedule(dynamic, 1)
        for (size_t b = 0; b < n0; b += BLOCK) RunPlan(p, b, std::min(n0, b + BLOCK), bind, body);
      }
    }
    if (delta_src) p.src[0] = delta_src;
    // 3. Head slots, serially (a generic table grows); then the edges, in parallel over partitions.
    size_t nrows = 0; for (auto& O : out) nrows += O.size();
    std::vector<size_t> hslot; hslot.reserve(nrows);
    std::vector<const num*> rowp; rowp.reserve(nrows);
    std::vector<int64_t> sslot; sslot.reserve(nrows * nsrc);  // source slots, allocated serially too (a left atom's key may be new to its state)
    for (auto& O : out) for (size_t r = 0; r < O.size(); r++) {
      const num* row = O.row(r);
      size_t hs = head.SlotOf(row); if (hs == ~size_t(0)) Fail("no slot for a key of " + head.name);
      hslot.push_back(hs); rowp.push_back(row);
      int off = nkeys;
      for (int i = 0; i < nsrc; i++) {
        const Atom& atom = rule.atoms[rec_atoms[i]];
        State& AS = states.at(atom.rel);
        int ar = AS.arity;
        bool wild = false; for (int c = 0; c < ar; c++) wild |= atom.args[c].kind == Expr::OP;
        if (wild) sslot.push_back(-1);
        else { size_t ss = AS.SlotOf(row + off); if (ss == ~size_t(0)) Fail("no slot for a source key of an edge of " + head.name); sslot.push_back((int64_t)ss); }
        off += ar;
      }
    }
    int nt_w = nrows < 2048 ? 1 : T;
#pragma omp parallel for num_threads(nt_w) schedule(static)
    for (int t = 0; t < T; t++) {
      EdgePart& P = E.part[t];
      auto& touched = E.touched[t];
      std::vector<int64_t> name(nw);
      for (size_t r = 0; r < nrows; r++) {
        size_t hs = hslot[r];
        if ((int)(hs % T) != t) continue;
        const num* row = rowp[r];
        name[0] = rule_index; name[nw - 1] = (int64_t)hs;
        for (int i = 1; i < nw - 1; i++) name[i] = -2;
        for (int i = 0; i < nsrc; i++) name[1 + i] = sslot[r * nsrc + i];
        int e = P.Find(name.data());
        if (e < 0) {
          e = P.Add(name.data());
          size_t hl = hs / T;
          if (P.in_edges.size() <= hl) { P.in_edges.resize(hl + 1); P.head_key.resize(hl + 1); }
          if (P.head_key[hl].empty()) P.head_key[hl].assign(row, row + nkeys);
          P.in_edges[hl].push_back({e, P.gen[e]}); P.head[e] = hs; touched.push_back(hs);
          int off = nkeys;
          for (int i = 0; i < nsrc; i++) {
            const Atom& atom = rule.atoms[rec_atoms[i]];
            int ar = states.at(atom.rel).arity;
            if (name[1 + i] < 0) P.out_any[{rule_index, rec_atoms[i]}][std::vector<num>(row + off, row + off + ar)].push_back({e, P.gen[e]});
            else { auto& lists = P.out_edges[{rule_index, rec_atoms[i]}]; size_t ss = name[1 + i]; if (lists.size() <= ss) lists.resize(ss + 1); lists[ss].push_back({e, P.gen[e]}); }
            off += ar;
          }
        }
        P.bag[e].insert(P.bag[e].end(), row + kw, row + kw + nv);
        if (by_diff) { std::vector<num>& d = E.diff[t][hs]; if (d.empty()) d.assign(nv, 0); for (int c = 0; c < nv; c++) if (!std::isnan(row[kw + c])) d[c] += row[kw + c]; }
      }
    }
    for (auto& O : out) O.data.clear();
    if (trace) fprintf(stderr, "    edges of %s rule %d from atom %d: %zu removed, %zu bodies\n", head.name.c_str(), rule_index, delta_at, removed, nrows);
  }

  void ApplySemiEdge(State& S, std::vector<Rows>& out) {
    EdgeStore& E = edge_store[S.name];
    if (E.T == 0) return;
    int T = E.T;
    for (auto& o : out) o.width = S.DeltaWidth();
    std::vector<std::vector<num>> logs(T);
    static const num present_value = 1;
    size_t ntouched = 0; for (auto& tv : E.touched) ntouched += tv.size();
    int nt_a = ntouched < 2048 ? 1 : T;
#pragma omp parallel for num_threads(nt_a) schedule(static)
    for (int t = 0; t < T; t++) {
      EdgePart& P = E.part[t];
      std::vector<size_t>& touched = E.touched[t];
      std::sort(touched.begin(), touched.end());
      touched.erase(std::unique(touched.begin(), touched.end()), touched.end());
      std::vector<num> all, acc(S.nv);
      bool by_diff = S.nv > 0 && getenv("SOCRATES_EDGE_DIFF"); for (Agg a : S.aggs) by_diff &= a == SUM;
      for (size_t hs : touched) {
        size_t hl = hs / T;
        if (hl >= P.in_edges.size()) continue;
        std::vector<std::pair<int, int>>& ins = P.in_edges[hl];
        const num* hk = P.head_key[hl].data();
        bool changed;
        if (by_diff) {
          // The head moves by the running difference of its edges; it stays as long as an edge is alive.
          size_t kept = 0; bool alive = false;
          for (auto& eg : ins) { int e = eg.first; if (P.dead[e] || P.gen[e] != eg.second) continue; ins[kept++] = eg; alive = true; }
          ins.resize(kept);
          auto d = E.diff[t].find(hs);
          if (!alive) changed = S.Set(hk, nullptr);
          else {
            size_t slot = S.FindSlot(hk);
            bool was = slot != ~size_t(0) && S.slots.alive[slot] == 1;
            for (int c = 0; c < S.nv; c++) acc[c] = (was ? S.slots.vals[slot * S.nv + c] : 0) + (d == E.diff[t].end() ? 0 : d->second[c]);
            changed = S.Set(hk, acc.data());
          }
          if (d != E.diff[t].end()) E.diff[t].erase(d);
          if (changed) { logs[t].insert(logs[t].end(), hk, hk + S.arity); for (int c = 0; c < 2 * S.nv; c++) logs[t].push_back(0); }
          continue;
        }
        all.clear();
        size_t kept = 0;
        for (auto& eg : ins) { int e = eg.first; if (P.dead[e] || P.gen[e] != eg.second) continue; ins[kept++] = eg; all.insert(all.end(), P.bag[e].begin(), P.bag[e].end()); }
        ins.resize(kept);
        if (S.exists) changed = S.Set(hk, all.empty() ? nullptr : &present_value);
        else changed = S.Set(hk, FoldBag(S, all, acc) ? acc.data() : nullptr);
        if (changed) { logs[t].insert(logs[t].end(), hk, hk + S.arity); for (int c = 0; c < 2 * S.nv; c++) logs[t].push_back(0); }
      }
      touched.clear();
    }
    for (auto& L : logs) S.next_delta.data.insert(S.next_delta.data.end(), L.begin(), L.end());
    for (auto& O : out) O.data.clear();
  }

  // ----------------------------------------------------------- classify
  // Decides how the component is evaluated, and why. A head can be pushed
  // into only if the graph of its bodies is constant: the keys and the
  // lookups of a rule never depend on a value that changes. Given that, the
  // algebra decides the tier: idempotent columns are merged (lattice), if
  // every contribution moves the way the head does; columns with inverses
  // take differences (group). Anything else makes the whole component
  // recompute. Demotions propagate: a lattice may only read lattices.
  std::string RuleText(const Rule& r) {
    std::string t = r.head + "(";
    for (size_t k = 0; k < r.keys.size(); k++) t += (k ? ", " : "") + ExprText(r.keys[k]);
    t += ")";
    if (!r.values.empty()) { t += " <- "; for (size_t v = 0; v < r.values.size(); v++) t += (v ? ", " : "") + ExprText(r.values[v]); }
    t += " :- ";
    for (size_t a = 0; a < r.atoms.size(); a++) {
      const Atom& atom = r.atoms[a];
      t += (a ? ", " : "") + std::string(atom.left ? "left " : "") + (atom.unnest ? "in" : atom.rel) + "(";
      for (size_t c = 0; c < atom.args.size(); c++) t += (c ? ", " : "") + ExprText(atom.args[c]);
      t += ")";
    }
    for (auto& c : r.conds) t += ", " + ExprText(c);
    return t;
  }
  std::string ExprText(const Expr& e) {
    if (e.kind == Expr::VAR) return "v" + std::to_string(e.var);
    if (e.kind == Expr::CONST) { if (std::isnan(e.value)) return "null"; char b[32]; snprintf(b, sizeof b, "%g", e.value); return b; }
    std::string t = e.op + "(";
    for (size_t i = 0; i < e.args.size(); i++) t += (i ? ", " : "") + ExprText(e.args[i]);
    return t + ")";
  }

  void Classify(bool lattice_opt, bool group_opt, bool walks) {
    // Candidate tier of every state from its algebra alone.
    std::map<std::string, State::Tier> tier;
    for (auto& kv : states) {
      State& S = kv.second;
      bool idem = true, inv = S.nv > 0;
      for (Agg a : S.aggs) { AggProps p = Props(a); idem &= p.idempotent; inv &= p.inverse; }
      tier[S.name] = idem && lattice_opt ? State::LATTICE : inv && group_opt ? State::GROUP : State::SEMI;
      if (tier[S.name] == State::SEMI) {
        std::string ops; for (Agg a : S.aggs) ops += std::string(ops.empty() ? "" : ", ") + Props(a).name;
        why[S.name] = S.nv == 0 ? "" : "aggregate " + ops + (idem ? " (lattice tier switched off)" : inv ? " (group tier switched off)" : " is neither idempotent nor invertible");
      }
    }
    bool component_ok = true;
    std::string component_why;
    // Demote until stable.
    for (bool changed = true; changed;) {
      changed = false;
      for (auto& rule : rules) {
        State& H = states.at(rule.head);
        State::Tier& ht = tier[H.name];
        // A failed check demotes the head to the semigroup tier; a body
        // whose graph is not constant takes the whole component to recomputation.
        auto fail = [&](const std::string& reason, bool whole = false) {
          std::string msg = reason + " in rule " + RuleText(rule);
          if (whole) { if (component_ok) component_why = msg; component_ok = false; }
          if (ht != State::SEMI) { ht = State::SEMI; why[H.name] = msg; changed = true; }
        };
        // Variables that carry a changing value: value columns of recursive
        // atoms (a left atom's value toggles with presence), and whatever
        // is computed from them.
        std::vector<char> recval(rule.nvars, 0);
        std::vector<std::pair<std::string, int>> source(rule.nvars, {"", -1});  // state, value column
        for (auto& atom : rule.atoms) {
          if (!atom.recursive) continue;
          int arity = states.at(atom.rel).arity;
          for (size_t c = arity; c < atom.args.size(); c++) if (atom.args[c].kind == Expr::VAR) { recval[atom.args[c].var] = 1; source[atom.args[c].var] = {atom.rel, atom.left ? -1 : (int)c - arity}; }
        }
        for (bool more = true; more;) {
          more = false;
          for (auto& l : rule.lets) { if (recval[l.first]) continue; std::vector<int> vs; ExprVars(l.second, vs); for (int v : vs) if (recval[v]) { recval[l.first] = 1; source[l.first] = {"", -2}; more = true; } }
          for (auto& atom : rule.atoms) if (atom.unnest) { int ev = atom.args[1].var; if (recval[ev]) continue; std::vector<int> vs; ExprVars(atom.args[0], vs); for (int v : vs) if (recval[v]) { recval[ev] = 1; source[ev] = {"", -2}; more = true; } }
        }
        auto depends = [&](const Expr& e) { std::vector<int> vs; ExprVars(e, vs); for (int v : vs) if (recval[v]) return true; return false; };
        // The graph of bodies must be constant, for every tier.
        // A key computed from a changing value moves a body between keys:
        // a push with both bindings follows it (the old contribution leaves
        // the old key), a merge cannot.
        for (auto& k : rule.keys) if (depends(k) && ht == State::LATTICE) fail("a head key depends on a changing value (a lattice cannot take a contribution back)");
        for (auto& atom : rule.atoms) {
          if (atom.unnest) { if (depends(atom.args[0]) && ht != State::SEMI) fail("a list under `in` depends on a changing value (only a push with both sides follows it)"); continue; }
          int arity = atom.recursive ? states.at(atom.rel).arity : (int)atom.args.size() - (atom.has_value ? 1 : 0);
          for (int c = 0; c < arity && c < (int)atom.args.size(); c++) if (depends(atom.args[c]) && ht != State::SEMI) fail("a lookup depends on a changing value (only a push with both sides follows it)");
        }
        int nrec = 0; for (auto& atom : rule.atoms) nrec += atom.recursive;
        bool conds_on_values = false;
        for (auto& c : rule.conds) conds_on_values |= depends(c);
        for (auto& l : rule.lets) if (depends(l.second) || recval[l.first]) {
          // A let whose variable is bound by an atom is an equality check.
          bool bound_by_atom = false;
          for (auto& atom : rule.atoms) for (auto& e : atom.args) if (e.kind == Expr::VAR && e.var == l.first) bound_by_atom = true;
          if (bound_by_atom) conds_on_values = true;
        }
        bool has_left = false; for (auto& atom : rule.atoms) has_left |= atom.left;
        // Sources that can vanish: a presence state that is not a lattice.
        bool vanishing = false;
        // Lattice and group keys stay once they exist; a semigroup key is gone when its bag empties.
        for (auto& atom : rule.atoms) if (atom.recursive && !atom.left && tier[atom.rel] == State::SEMI) vanishing = true;
        if (ht == State::LATTICE) {
          // Bodies may only appear, and every contribution must move the
          // head's way: the source's direction composed with the expression.
          if (conds_on_values) fail("a condition depends on a changing value (a lattice cannot take a contribution back)");
          if (has_left) fail("reads an aggregating expression, whose value can go both ways");
          if (vanishing) fail("reads a predicate whose facts can disappear");
          for (size_t col = 0; col < rule.values.size() && ht == State::LATTICE; col++) {
            Agg a = H.aggs[col];
            int want = a == MIN ? -1 : a == MAX ? 1 : 0;  // ArgMin/ArgMax columns follow their Min/Max
            for (int v = 0; v < rule.nvars && ht == State::LATTICE; v++) {
              if (!recval[v]) continue;
              int m = MonoIn(rule.values[col], v);
              if (m == 0) continue;
              auto src = source[v];
              int dir = 2;
              if (src.second >= 0 && tier[src.first] == State::LATTICE) { Agg sa = states.at(src.first).aggs[src.second]; dir = sa == MIN ? -1 : sa == MAX ? 1 : 2; }
              int moves = (dir == 2 || m == 2) ? 2 : dir * m;
              if (want == 0 ? moves != 0 && dir == 2 : moves != want)
                fail(std::string("contribution ") + ExprText(rule.values[col]) + " does not move the way " + Props(a).name + " does");
            }
          }
        } else if (ht == State::GROUP) {
          if (nrec > 1) fail("joins two changing predicates (a difference cannot follow their joint change)");
          if (conds_on_values) fail("a condition depends on a changing value");
          if (has_left) fail("reads an aggregating expression");
          if (vanishing) fail("reads a predicate whose facts can disappear");
        }
      }
    }
    mode = component_ok || walks ? DIFFERENTIAL : RECOMPUTE;
    if (getenv("SOCRATES_MODE") && !strcmp(getenv("SOCRATES_MODE"), "recompute")) { mode = RECOMPUTE; component_why = "SOCRATES_MODE=recompute"; component_ok = false; }  // experiment
    for (auto& kv : states) {
      State::Tier t = tier[kv.first];
      if (walks && t == State::SEMI) t = State::BLACKBOX;  // the historical path: marks and recomputation per key
      kv.second.tier = mode == RECOMPUTE ? State::BLACKBOX : t;
    }
    if (getenv("SOCRATES_EXPLAIN") || getenv("SOCRATES_TRACE")) {
      fprintf(stderr, "socrates: component evaluated by %s\n", mode == RECOMPUTE ? "recomputation (every predicate whole, every pass)" : "pushing changes (the graph of bodies is constant)");
      if (!component_ok) fprintf(stderr, "  because %s\n", component_why.c_str());
      for (auto& kv : states) {
        State::Tier t = tier[kv.first];
        const char* label = t == State::LATTICE ? "lattice (merge)" : t == State::GROUP ? "group (difference)" : walks ? "semigroup (recompute affected keys)" : "semigroup (replace the contribution, fold again)";
        if (mode == RECOMPUTE) fprintf(stderr, "  %s: recomputed (its own algebra: %s)%s%s\n", kv.first.c_str(), label, why[kv.first].empty() ? "" : "; ", why[kv.first].c_str());
        else fprintf(stderr, "  %s: %s%s%s\n", kv.first.c_str(), label, why[kv.first].empty() ? "" : "; ", why[kv.first].c_str());
      }
    }
  }

  // ----------------------------------------------------------------- run
  Type ReadType(const Json& j) {
    Type t;
    if (j.kind == Json::STR) {
      t.kind = j.str == "num" ? Type::NUM : j.str == "str" ? Type::STR : Type::ANY;
    } else if (j.kind == Json::OBJ) {
      if (const Json* e = j.Get("array")) { t.kind = Type::ARRAY; t.elem.push_back(ReadType(*e)); }
      else if (const Json* f = j.Get("record")) { t.kind = Type::RECORD; for (auto& kv : f->obj) t.fields.emplace_back(kv.first, ReadType(kv.second)); }
    }
    return t;
  }

  // CSV field at data[i..): unquoted up to the separator, or quoted with
  // doubled quotes. Advances i past the field (not the separator).
  static std::string CsvField(const char* data, size_t n, size_t& i) {
    std::string r;
    if (i < n && data[i] == '"') {
      i++;
      while (i < n) {
        if (data[i] == '"') { if (i + 1 < n && data[i + 1] == '"') { r += '"'; i += 2; continue; } i++; break; }
        r += data[i++];
      }
    } else {
      while (i < n && data[i] != ',' && data[i] != '\n' && data[i] != '\r') r += data[i++];
    }
    return r;
  }

  void LoadDictionary(const std::string& path) {
    FILE* f = fopen(path.c_str(), "r"); if (!f) Fail("cannot open " + path);
    std::string text; char buf[65536]; size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0) text.append(buf, n);
    fclose(f);
    size_t i = 0;
    while (i < text.size()) {
      std::string id = CsvField(text.data(), text.size(), i);
      if (i < text.size() && text[i] == ',') i++;
      std::string s = CsvField(text.data(), text.size(), i);
      while (i < text.size() && text[i] != '\n') i++;
      i++;
      if (id.empty()) continue;
      size_t k = atoi(id.c_str());
      if (dict.text.size() <= k) dict.text.resize(k + 1);
      dict.text[k] = s; dict.id[s] = k;
    }
    dict.given = dict.text.size() - 1;
  }

  // Rows of a CSV with composite (JSON) columns: a plain reader.
  Rows ReadCsvWithValues(const std::string& path, const std::vector<Type>& types) {
    Rows R; R.width = types.size();
    FILE* f = fopen(path.c_str(), "r"); if (!f) Fail("cannot open " + path);
    std::string text; char buf[65536]; size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0) text.append(buf, n);
    fclose(f);
    size_t i = 0;
    while (i < text.size()) {
      if (text[i] == '\n' || text[i] == '\r') { i++; continue; }
      for (int c = 0; c < R.width; c++) {
        std::string field = CsvField(text.data(), text.size(), i);
        if (i < text.size() && text[i] == ',') i++;
        num v;
        if (field.empty()) { v = NONE; R.has_null = true; }
        else if (types[c].Composite()) { JsonReader jr(field.c_str(), arena, dict); v = jr.Value(types[c]); }
        else v = strtod(field.c_str(), nullptr);
        R.data.push_back(v);
      }
      while (i < text.size() && text[i] != '\n') i++;
      i++;
    }
    return R;
  }

  std::string Run(const Json& spec) {
    threads = spec.Get("threads") ? (int)spec.At("threads").num : omp_get_max_threads();
    omp_set_num_threads(threads);
    g_arena = &arena; g_dict = &dict;
    const Json* dictionary = spec.Get("dictionary");
    if (dictionary && dictionary->kind != Json::OBJ) dictionary = nullptr;
    if (dictionary) LoadDictionary(dictionary->At("file").str);
    int max_rounds = spec.Get("max_rounds") ? (int)spec.At("max_rounds").num : 1000000000;
    num eps = spec.Get("epsilon") ? spec.At("epsilon").num : 1e-12;
    double t0 = Now();
    bool any = false;
    for (auto& kv : spec.At("relations").obj) {
      const Json& r = kv.second;
      int arity = (int)r.At("arity").num;
      std::vector<Type> types;
      if (r.Get("types")) for (auto& t : r.At("types").arr) types.push_back(ReadType(t));
      if (r.At("kind").str == "input") {
        int nv = r.Get("values") ? (int)r.At("values").num : (r.Get("value") && r.At("value").b ? 1 : 0);
        bool composite = false; for (auto& t : types) composite |= t.Composite();
        if (composite && (int)types.size() != arity + nv) Fail("types of " + kv.first + " do not match its width");
        Rows R = composite ? ReadCsvWithValues(r.At("file").str, types) : ReadCsv(r.At("file").str, arity + nv);
        input_types[kv.first] = types;
        for (size_t i = 0; i < R.size(); i++) for (int c = 0; c < arity; c++) {
          i64 x = (i64)R.row(i)[c];
          if (!any || x < domain_lo) domain_lo = x;
          if (!any || x > domain_hi) domain_hi = x;
          any = true;
        }
        inputs[kv.first] = std::move(R);
      } else {
        State S; S.name = kv.first; S.arity = arity; S.eps = eps;
        S.stop = r.Get("stop") && r.At("stop").b;
        S.internal = r.Get("internal") && r.At("internal").b;
        S.types = types;
        if (r.Get("hidden")) for (auto& h : r.At("hidden").arr) { size_t c = (size_t)h.num; if (S.hidden.size() <= c) S.hidden.resize(c + 1, false); S.hidden[c] = true; }
        if (r.Get("aggs")) for (auto& a : r.At("aggs").arr) S.aggs.push_back(ParseAgg(a.str));
        else if (r.Get("agg") && r.At("agg").str != "or") S.aggs.push_back(ParseAgg(r.At("agg").str));
        S.nv = S.aggs.size();
        states[kv.first] = std::move(S);
      }
    }
    for (auto& rj : spec.At("rules").arr) {
      std::map<std::string, int> vars;
      Rule rule; rule.head = rj.At("head").str;
      for (auto& k : rj.At("keys").arr) rule.keys.push_back(ReadExpr(k, vars));
      if (rj.Get("values")) for (auto& v : rj.At("values").arr) rule.values.push_back(ReadExpr(v, vars));
      else if (rj.Get("value") && rj.At("value").kind != Json::NUL) rule.values.push_back(ReadExpr(rj.At("value"), vars));
      if ((int)rule.values.size() != states.at(rule.head).nv) Fail("a rule of " + rule.head + " has the wrong number of values");
      for (auto& aj : rj.At("atoms").arr) {
        Atom atom; atom.rel = aj.At("rel").str;
        atom.unnest = atom.rel == "__unnest";
        atom.recursive = !atom.unnest && states.count(atom.rel) > 0;
        atom.has_value = aj.Get("has_value") && aj.At("has_value").b;
        atom.left = aj.Get("left") && aj.At("left").b;
        for (auto& arg : aj.At("args").arr) {
          if (arg.kind == Json::NUL) { Expr e; e.kind = Expr::OP; e.op = "_"; atom.args.push_back(e); }
          else atom.args.push_back(ReadExpr(arg, vars));
        }
        rule.atoms.push_back(atom);
      }
      if (rj.Get("conds")) for (auto& c : rj.At("conds").arr) rule.conds.push_back(ReadExpr(c, vars));
      if (rj.Get("lets")) for (auto& l : rj.At("lets").arr) { Expr v = ReadExpr(l.At("var"), vars); rule.lets.emplace_back(v.var, ReadExpr(l.At("expr"), vars)); }
      rule.nvars = vars.size();
      std::function<void(const Expr&)> widen = [&](const Expr& e) {
        if (e.kind == Expr::CONST) { i64 v = (i64)e.value; if (!any || v < domain_lo) domain_lo = v; if (!any || v > domain_hi) domain_hi = v; any = true; }
        for (auto& a : e.args) widen(a);
      };
      for (auto& k : rule.keys) widen(k);
      for (auto& a : rule.atoms) for (auto& e : a.args) widen(e);
      rules.push_back(std::move(rule));
    }
    // Retractable states: a left atom makes a head's facts revisable, and
    // so are the facts of everything reading such a state. Retractable
    // sets keep an existence value, so that their log can say "gone".
    for (bool changed = true; changed;) {
      changed = false;
      for (auto& rule : rules) {
        State& head = states.at(rule.head);
        if (head.retractable) continue;
        for (auto& a : rule.atoms) if (a.left || (a.recursive && states.at(a.rel).retractable)) { head.retractable = true; changed = true; break; }
      }
    }
    for (auto& rule : rules) {
      int nrec = 0; for (auto& a : rule.atoms) nrec += a.recursive;
      if (nrec > 1) states.at(rule.head).joins_states = true;
    }
    for (auto& kv : states) if (kv.second.retractable && kv.second.nv == 0) {
      kv.second.exists = true;
      kv.second.nv = 1; kv.second.aggs.assign(1, ASSIGN);  // the presence value, so that the log can say "gone"
      for (auto& rule : rules) if (rule.head == kv.first) { Expr one; one.kind = Expr::CONST; one.value = 1; rule.values.push_back(one); }
    }
    auto flag = [](const char* name) { const char* v = getenv(name); return !(v && (!strcmp(v, "false") || !strcmp(v, "0"))); };
    bool lattice_opt = flag("SOCRATIC_LATTICE_OPT"), group_opt = flag("SOCRATIC_GROUP_OPT");
    bool walks = getenv("SOCRATES_SEMIGROUP") && !strcmp(getenv("SOCRATES_SEMIGROUP"), "walks");
    Classify(lattice_opt, group_opt, walks);
    // A presence predicate on the semigroup tier (the lattice tier switched
    // off) needs the presence value too, like a retractable one above.
    for (auto& kv : states) if (kv.second.tier == State::SEMI && kv.second.nv == 0 && !kv.second.exists) {
      kv.second.exists = true;
      kv.second.nv = 1; kv.second.aggs.assign(1, ASSIGN);
      for (auto& rule : rules) if (rule.head == kv.first) { Expr one; one.kind = Expr::CONST; one.value = 1; rule.values.push_back(one); }
    }
    // Which states may hold keys outside the input domain (computed by an
    // expression, or taken from a value column, or from such a column of
    // another state): they use the generic storage. A fixpoint over the
    // rules propagates "unsafe" from state columns to the heads bound
    // from them.
    std::map<std::string, std::vector<bool>> unsafe;  // state -> per key column
    for (auto& kv : states) unsafe[kv.first].assign(kv.second.arity, false);
    for (bool changed = true; changed;) {
      changed = false;
      for (auto& rule : rules) {
        std::vector<bool>& head = unsafe[rule.head];
        for (size_t k = 0; k < rule.keys.size(); k++) {
          if (head[k]) continue;
          bool bad = rule.keys[k].kind != Expr::VAR;
          if (!bad) {
            // Where is the key's variable bound? The first atom column
            // mentioning it; a value column or an unsafe state column taints it.
            bool found = false;
            for (auto& atom : rule.atoms) {
              if (atom.unnest) continue;  // elements of a list: anything
              int arity = atom.recursive ? states.at(atom.rel).arity : (int)atom.args.size() - (atom.has_value ? 1 : 0);
              for (size_t c = 0; c < atom.args.size() && !found; c++) {
                if (atom.args[c].kind != Expr::VAR || atom.args[c].var != rule.keys[k].var) continue;
                found = true;
                if ((int)c >= arity) bad = true;                                  // a value column
                else if (atom.recursive && unsafe[atom.rel][c]) bad = true;     // an unsafe state column
              }
              if (found) break;
            }
            if (!found) bad = true;  // bound by a let or a condition
          }
          if (bad) { head[k] = true; changed = true; }
        }
      }
    }
    std::set<std::string> computed_keys;
    for (auto& kv : unsafe) for (bool b : kv.second) if (b) computed_keys.insert(kv.first);
    for (auto& kv : states) kv.second.Init(domain_lo, domain_hi, threads, kv.second.tier, computed_keys.count(kv.first) > 0);
    if (trace) for (auto& kv : states) { State& S = kv.second; fprintf(stderr, "state %s: %s, tier %d, nv %d%s\n", S.name.c_str(), S.dense ? "dense" : S.dense2 ? "dense2" : S.packed ? "packed" : "generic", (int)S.tier, S.nv, S.exists ? ", exists" : ""); }
    // States read in full each round: by a non-linear rule, or by the
    // recomputation of a black-box head.
    std::set<std::string> needs_full;
    for (auto& rule : rules) {
      int nrec = 0; for (auto& a : rule.atoms) nrec += a.recursive;
      if (nrec > 1 || states.at(rule.head).tier == State::BLACKBOX || mode == RECOMPUTE) for (auto& a : rule.atoms) if (a.recursive) needs_full.insert(a.rel);
      for (auto& a : rule.atoms) if (a.left) needs_full.insert(a.rel);
    }
    double t1 = Now();

    std::vector<Rows> out(threads);
    // Members in diamond order; a pass evaluates each member once, in
    // order, every rule consuming the changes of its body relations it
    // has not seen yet (changes made earlier in the same pass included).
    std::vector<State*> members;
    if (spec.Get("order")) for (auto& n : spec.At("order").arr) members.push_back(&states.at(n.str));
    else for (auto& kv : states) members.push_back(&kv.second);
    for (size_t i = 0; i < members.size(); i++) members[i]->order = i;
    std::map<std::string, std::vector<const Rule*>> rules_of;
    for (auto& rule : rules) rules_of[rule.head].push_back(&rule);
    // cursor[rule][atom]: rows of that relation's log already consumed.
    std::map<const Rule*, std::vector<size_t>> cursor;
    for (auto& rule : rules) cursor[&rule].assign(rule.atoms.size(), 0);
    int rounds = 0;
    double t_push = 0, t_collect = 0, t_mark = 0, t_pull = 0, t_close = 0, t_snap = 0;
    // The memory the engine itself holds, checked once per pass: past
    // SOCRATES_MEM_GB (60 by default) the run fails cleanly instead of
    // pushing the machine into swap.
    static const double mem_limit_gb = getenv("SOCRATES_MEM_GB") ? atof(getenv("SOCRATES_MEM_GB")) : 60.0;
    auto footprint_gb = []() -> double {
#ifdef __APPLE__
      task_vm_info_data_t info; mach_msg_type_number_t n = TASK_VM_INFO_COUNT;
      if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &n) == KERN_SUCCESS) return (double)info.phys_footprint / (1ULL << 30);
#endif
      return 0.0;
    };
    while (rounds < max_rounds) {
      rounds++;
      if (mem_limit_gb > 0) { double gb = footprint_gb(); if (gb > mem_limit_gb) Fail("memory limit: the engine holds " + std::to_string((int)gb) + " GB, SOCRATES_MEM_GB is " + std::to_string((int)mem_limit_gb)); }
      double tr = Now();
      bool progress = false;
      long long changed = 0;
      for (State* member : members) {
        State& S = *member;
        double ts = Now();
        S.Snapshot();
        state_index.clear();
        full_state.clear();
        (void)needs_full;  // materialized copies are made when a plan needs them (FullState)
        t_snap += Now() - ts;
        if (mode == RECOMPUTE || (semigroup_full && S.tier == State::BLACKBOX)) {
          // Consume the logs (cursors) without acting on them, then recompute whole.
          for (const Rule* rule : rules_of[S.name]) for (size_t a = 0; a < rule->atoms.size(); a++) if (rule->atoms[a].recursive) cursor[rule][a] = states.at(rule->atoms[a].rel).log.size();
          double tq = Now(); FullRecompute(S, out); t_pull += Now() - tq;
          size_t before0 = S.log.size(); S.CloseRound();
          if (S.log.size() > before0) progress = true;
          changed += S.log.size() - before0;
          continue;
        }
        for (const Rule* rule : rules_of[S.name]) {
          int rule_index = rule - &rules[0];
          bool rec = false, regular = false;
          int nrec_atoms = 0;
          for (auto& a : rule->atoms) { rec |= a.recursive; regular |= a.recursive && !a.left; nrec_atoms += a.recursive; }
          // Without a regular state atom the rule has matches before any
          // change (a left atom matches by absence): evaluated in full
          // once, its left atoms' changes so far consumed.
          if (!regular && rounds == 1) {
            if (S.tier == State::SEMI) { if (semi_edge) PushSemiEdge(*rule, rule_index, -1, out); else PushSemi(*rule, -1, out); }
            else if (S.tier != State::BLACKBOX) { Push(*rule, -1, out); Collect(S, out); }
            else if (store_contrib) StoreAffected(*rule, -1);
            else MarkAffected(*rule, -1);
            for (size_t a = 0; a < rule->atoms.size(); a++) if (rule->atoms[a].left) cursor[rule][a] = states.at(rule->atoms[a].rel).log.size();
          }
          if (S.tier == State::SEMI && nrec_atoms > 1 && semi_edge) {
            // Edges are named by all changing atoms: each atom's changes rewrite its edges, no state "before" needed.
            for (size_t a = 0; a < rule->atoms.size(); a++) {
              if (!rule->atoms[a].recursive) continue;
              State& B = states.at(rule->atoms[a].rel);
              size_t from = cursor[rule][a], to = B.log.size();
              cursor[rule][a] = to;
              if (from == to) continue;
              B.delta.width = B.log.width;
              B.delta.data.assign(B.log.data.begin() + from * B.log.width, B.log.data.begin() + to * B.log.width);
              for (auto it = state_index.begin(); it != state_index.end();) { if (it->first.first == B.name + "#delta") it = state_index.erase(it); else ++it; }
              double tp = Now(); PushSemiEdge(*rule, rule_index, a, out); t_push += Now() - tp;
            }
            continue;
          }
          if (S.tier == State::SEMI && nrec_atoms > 1) {
            // Ranges first, then one atom at a time with the earlier atoms as they were.
            std::vector<std::pair<size_t, size_t>> range(rule->atoms.size(), {0, 0});
            for (size_t a = 0; a < rule->atoms.size(); a++) if (rule->atoms[a].recursive) { State& B = states.at(rule->atoms[a].rel); range[a] = {cursor[rule][a], B.log.size()}; cursor[rule][a] = range[a].second; }
            for (size_t a = 0; a < rule->atoms.size(); a++) {
              if (!rule->atoms[a].recursive || range[a].first == range[a].second) continue;
              State& B = states.at(rule->atoms[a].rel);
              B.delta.width = B.log.width;
              B.delta.data.assign(B.log.data.begin() + range[a].first * B.log.width, B.log.data.begin() + range[a].second * B.log.width);
              for (auto it = state_index.begin(); it != state_index.end();) { if (it->first.first == B.name + "#delta" || it->first.first.find("#before") != std::string::npos) it = state_index.erase(it); else ++it; }
              plan_before_atoms.clear(); before_state.clear(); before_overlay.clear();
              for (size_t j = 0; j < a; j++) if (rule->atoms[j].recursive && range[j].first != range[j].second) {
                plan_before_atoms.insert(j);
                State& Bj = states.at(rule->atoms[j].rel);
                if (!before_overlay.count(Bj.name)) {
                  auto& ov = before_overlay[Bj.name];
                  int ba = Bj.arity, bnv = Bj.nv;
                  for (size_t r = range[j].first; r < range[j].second; r++) {
                    const num* row = Bj.log.row(r);
                    std::vector<num> key(row, row + ba);
                    if (bnv == 0 || std::isnan(row[ba + bnv])) ov[key] = std::vector<num>();  // appeared: was absent
                    else { std::vector<num> old(row, row + ba); old.insert(old.end(), row + ba + bnv, row + ba + 2 * bnv); ov[key] = old; }
                  }
                }
              }
              double tp = Now();
              PushSemi(*rule, a, out);
              t_push += Now() - tp;
              plan_before_atoms.clear(); before_state.clear(); before_overlay.clear();
            }
            continue;
          }
          if (!rec) continue;
          for (size_t a = 0; a < rule->atoms.size(); a++) {
            if (!rule->atoms[a].recursive) continue;
            State& B = states.at(rule->atoms[a].rel);
            size_t from = cursor[rule][a], to = B.log.size();
            cursor[rule][a] = to;
            if (from == to) continue;
            B.delta.width = B.log.width;
            B.delta.data.assign(B.log.data.begin() + from * B.log.width, B.log.data.begin() + to * B.log.width);
            state_index.erase(std::make_pair(B.name + "#delta", std::vector<int>{0}));
            for (auto it = state_index.begin(); it != state_index.end();) { if (it->first.first == B.name + "#delta") it = state_index.erase(it); else ++it; }
            if (trace) fprintf(stderr, "  %s <- %s: %zu changed rows\n", rule->head.c_str(), B.name.c_str(), to - from);
            double tp = Now();
            if (S.tier == State::SEMI) { if (semi_edge) PushSemiEdge(*rule, rule_index, a, out); else PushSemi(*rule, a, out); t_push += Now() - tp; }
            else if (S.tier != State::BLACKBOX) { Push(*rule, a, out); t_push += Now() - tp; tp = Now(); Collect(S, out); t_collect += Now() - tp; }
            else if (store_contrib) { StoreAffected(*rule, a); t_mark += Now() - tp; }
            else if (mark_all && rounds > 1) { S.MarkAllAlive(); }
            else { MarkAffected(*rule, a); t_mark += Now() - tp; }
          }
        }
        double tq = Now();
        if (S.tier == State::SEMI) { if (semi_edge) ApplySemiEdge(S, out); else ApplySemi(S, out); }
        else if (S.tier == State::BLACKBOX) { if (store_contrib && S.nv == 1) FoldStored(S, out); else Pull(S, out); }
        double t_apply = Now() - tq;
        t_pull += t_apply;
        size_t before = S.log.size();
        size_t pending = S.next_delta.size();
        tq = Now();
        S.CloseRound();
        t_close += Now() - tq;
        if (trace) fprintf(stderr, "  %s: %zu queued, %zu logged (apply %.3f s)\n", S.name.c_str(), pending, S.log.size() - before, t_apply);
        if (S.log.size() > before) progress = true;
        changed += S.log.size() - before;
      }
      if (on_pass && progress) on_pass(rounds, changed);
      bool stopped = false;
      for (State* member : members) if (member->stop && member->Materialize().size() > 0) stopped = true;
      if (stopped) break;
      // Logs are consumed by every rule reading them: drop what all have seen.
      for (auto& kv : states) {
        State& S = kv.second;
        size_t low = S.log.size();
        for (auto& rule : rules) for (size_t a = 0; a < rule.atoms.size(); a++) if (rule.atoms[a].rel == S.name && rule.atoms[a].recursive) low = std::min(low, cursor[&rule][a]);
        if (low > 0) {
          S.log.data.erase(S.log.data.begin(), S.log.data.begin() + low * S.log.width);
          for (auto& rule : rules) for (size_t a = 0; a < rule.atoms.size(); a++) if (rule.atoms[a].rel == S.name && rule.atoms[a].recursive) cursor[&rule][a] -= low;
        }
      }
      if (trace) fprintf(stderr, "pass %d %.3f s (push %.3f collect %.3f mark %.3f pull %.3f close %.3f snapshot %.3f)\n", rounds, Now() - tr, t_push, t_collect, t_mark, t_pull, t_close, t_snap);
      t_push = t_collect = t_mark = t_pull = t_close = t_snap = 0;
      if (!progress) { rounds--; break; }  // an empty pass is not counted
    }
    double t2 = Now();
    return Finish(spec, rounds, max_rounds, t0, t1, t2);
  }

  std::string Finish(const Json& spec, int rounds, int max_rounds, double t0, double t1, double t2) {
    std::string stats = "{\"iterations\": " + std::to_string(rounds) + ", \"converged\": " + (rounds < max_rounds ? "true" : "false");
    for (auto& kv : spec.At("relations").obj) {
      if (kv.second.At("kind").str == "input") continue;
      State& S = states.at(kv.first);
      if (S.internal) continue;
      Rows R = S.Materialize();
      int ncols = S.exists ? S.arity : R.width;
      std::vector<int> cols;  // written columns
      for (int c = 0; c < ncols; c++) if (c < S.arity || S.hidden.size() <= (size_t)(c - S.arity) || !S.hidden[c - S.arity]) cols.push_back(c);
      std::vector<const Type*> ctype(ncols, nullptr);
      for (int c = 0; c < ncols && c < (int)S.types.size(); c++) ctype[c] = &S.types[c];
      FILE* f = fopen(kv.second.At("out").str.c_str(), "w");
      if (!f) Fail("cannot write " + kv.second.At("out").str);
      size_t nrows = R.size();
      std::vector<std::string> chunk(threads);
#pragma omp parallel num_threads(threads)
      {
        int t = omp_get_thread_num();
        size_t lo_r = nrows * t / threads, hi_r = nrows * (t + 1) / threads;
        std::string& buf = chunk[t];
        buf.reserve((hi_r - lo_r) * 12);
        char tmp[24], ftmp[40];
        for (size_t i = lo_r; i < hi_r; i++) {
          const num* row = R.row(i);
          for (size_t ci = 0; ci < cols.size(); ci++) {
            int c = cols[ci];
            num x = row[c];
            char end = ci + 1 == cols.size() ? '\n' : ',';
            if (std::isnan(x)) {
              buf.push_back(end);  // null: an empty field
            } else if (ctype[c] && ctype[c]->Composite()) {
              std::string json; ToJson(x, *ctype[c], arena, dict, json);
              buf.push_back('"');
              for (char ch : json) { if (ch == '"') buf.push_back('"'); buf.push_back(ch); }
              buf.push_back('"'); buf.push_back(end);
            } else if (x == (num)(i64)x && x > -9e15 && x < 9e15) {
              i64 v = (i64)x;
              uint64_t u = v < 0 ? (uint64_t)(-(v + 1)) + 1 : (uint64_t)v;
              int p = sizeof tmp;
              tmp[--p] = end;
              do { tmp[--p] = '0' + (u % 10); u /= 10; } while (u);
              if (v < 0) tmp[--p] = '-';
              buf.append(tmp + p, sizeof tmp - p);
            } else {
              int len = snprintf(ftmp, sizeof ftmp, "%.17g%c", x, end);
              buf.append(ftmp, len);
            }
          }
        }
      }
      for (auto& buf : chunk) fwrite(buf.data(), 1, buf.size(), f);
      fclose(f);
      // Per written column: are all numbers whole (inside composites too)?
      std::vector<bool> integral(cols.size(), true);
      std::function<bool(num, const Type*)> whole = [&](num x, const Type* t) -> bool {
        if (std::isnan(x)) return true;
        if (t && t->kind == Type::STR) return true;
        if (t && t->Composite()) {
          if (!arena.Valid(x)) return true;
          const num* e = arena.Elems(x); size_t n = arena.Size(x);
          if (t->kind == Type::ARRAY) { for (size_t i = 0; i < n; i++) if (!whole(e[i], t->elem.empty() ? nullptr : &t->elem[0])) return false; return true; }
          for (size_t i = 0; i + 1 < n; i += 2) {
            const Type* ft = nullptr;
            for (auto& f : t->fields) { auto it = dict.id.find(f.first); if (it != dict.id.end() && it->second == (int)e[i]) ft = &f.second; }
            if (!whole(e[i + 1], ft)) return false;
          }
          return true;
        }
        return x == (num)(i64)x && x > -9e15 && x < 9e15;
      };
      for (size_t ci = 0; ci < cols.size(); ci++)
        for (size_t i = 0; i < nrows && integral[ci]; i++) integral[ci] = whole(R.row(i)[cols[ci]], ctype[cols[ci]]);
      stats += ", \"" + kv.first + "\": " + std::to_string(R.size());
      stats += ", \"" + kv.first + "_integral\": [";
      for (size_t ci = 0; ci < cols.size(); ci++) stats += std::string(ci ? "," : "") + (integral[ci] ? "true" : "false");
      stats += "]";
    }
    // Strings first met inside composite values: reported for the SQL side.
    const Json* d = spec.Get("dictionary");
    if (d && d->kind == Json::OBJ) {
      FILE* f = fopen(d->At("out").str.c_str(), "w");
      if (!f) Fail("cannot write " + d->At("out").str);
      for (size_t k = dict.given + 1; k < dict.text.size(); k++) {
        fprintf(f, "%zu,\"", k);
        for (char ch : dict.text[k]) { if (ch == '"') fputc('"', f); fputc(ch, f); }
        fputs("\"\n", f);
      }
      fclose(f);
    }
    double t3 = Now();
    stats += ", \"index_s\": " + std::to_string(index_s);
    stats += ", \"load_s\": " + std::to_string(t1 - t0) + ", \"eval_s\": " + std::to_string(t2 - t1) + ", \"write_s\": " + std::to_string(t3 - t2) + "}";
    return stats;
  }
};

}  // namespace

#include <csignal>
static void OnCrash(int sig) {
  const char msg[] = "socrates: internal error (crash); set SOCRATES_TRACE=1 and report the program\n";
  write(2, msg, sizeof msg - 1);
  _exit(2);
}

static void ReportPass(int pass, long long changed) {
  printf("pass %d %lld\n", pass, changed);
  fflush(stdout);
}

// Usage: socrates spec.json. Every pass is reported on stdout ("pass N
// changed"), the run's statistics come last as a JSON line; errors go to
// stderr with a non-zero exit.
int main(int argc, char** argv) {
  if (!getenv("SOCRATES_NO_HANDLER")) { signal(SIGSEGV, OnCrash); signal(SIGBUS, OnCrash); signal(SIGABRT, OnCrash); }  // debugging: let a sanitizer report
  if (argc < 2) { fprintf(stderr, "usage: socrates spec.json\n"); return 1; }
  FILE* f = fopen(argv[1], "r"); if (!f) { perror("spec"); return 1; }
  std::string text; char buf[65536]; size_t n;
  while ((n = fread(buf, 1, sizeof buf, f)) > 0) text.append(buf, n);
  fclose(f);
  JsonParser p(text.c_str());
  Json spec = p.Parse();
  Engine engine;
  engine.on_pass = ReportPass;
  std::string stats = engine.Run(spec);
  printf("%s\n", stats.c_str());
  return 0;
}
