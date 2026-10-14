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
// and called through ctypes. The component arrives as a JSON spec:
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
#include <vector>
#include <chrono>
#ifdef _OPENMP
#include <omp.h>
#else
static int omp_get_max_threads() { return 1; }
static int omp_get_thread_num() { return 0; }
static void omp_set_num_threads(int) {}
#endif

namespace {

typedef int64_t i64;
typedef double num;  // row scalar: integers are exact up to 2^53
const num NONE = std::numeric_limits<num>::quiet_NaN();

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
  enum Op { ADD, SUB, MUL, DIV, MOD, LT, LE, GT, GE, EQ, NE, AND, OR, NOT, NEG, ABS, LEAST, GREATEST, TOFLOAT, TOINT, FLOOR, UNKNOWN } opcode = UNKNOWN;
  int var = -1;
  num value = 0;
  std::string op;
  std::vector<Expr> args;
};

Expr::Op OpCode(const std::string& o, size_t nargs) {
  if (o == "+") return Expr::ADD;
  if (o == "-") return nargs == 1 ? Expr::NEG : Expr::SUB;
  if (o == "*") return Expr::MUL;
  if (o == "/") return Expr::DIV;
  if (o == "%") return Expr::MOD;
  if (o == "<") return Expr::LT;
  if (o == "<=") return Expr::LE;
  if (o == ">") return Expr::GT;
  if (o == ">=") return Expr::GE;
  if (o == "==") return Expr::EQ;
  if (o == "!=") return Expr::NE;
  if (o == "&&") return Expr::AND;
  if (o == "||") return Expr::OR;
  if (o == "!") return Expr::NOT;
  if (o == "Abs") return Expr::ABS;
  if (o == "Least") return Expr::LEAST;
  if (o == "Greatest") return Expr::GREATEST;
  if (o == "ToFloat64") return Expr::TOFLOAT;
  if (o == "ToInt64") return Expr::TOINT;
  if (o == "Floor") return Expr::FLOOR;
  return Expr::UNKNOWN;
}

num Eval(const Expr& e, const num* bind) {
  switch (e.kind) {
    case Expr::VAR: return bind[e.var];
    case Expr::CONST: return e.value;
    case Expr::OP: {
      num a = Eval(e.args[0], bind);
      switch (e.opcode) {
        case Expr::NOT: return !a;
        case Expr::NEG: return -a;
        case Expr::ABS: return a < 0 ? -a : a;
        case Expr::TOFLOAT: return a;
        case Expr::TOINT: return (num)(i64)a;
        case Expr::FLOOR: return std::floor(a);
        default: break;
      }
      num b = Eval(e.args[1], bind);
      switch (e.opcode) {
        case Expr::ADD: return a + b;
        case Expr::SUB: return a - b;
        case Expr::MUL: return a * b;
        case Expr::DIV: return a / b;
        case Expr::MOD: return b ? (num)((i64)a % (i64)b) : 0;
        case Expr::LT: return a < b;
        case Expr::LE: return a <= b;
        case Expr::GT: return a > b;
        case Expr::GE: return a >= b;
        case Expr::EQ: return a == b;
        case Expr::NE: return a != b;
        case Expr::AND: return a && b;
        case Expr::OR: return a || b;
        case Expr::LEAST: return a < b ? a : b;
        case Expr::GREATEST: return a > b ? a : b;
        default: Fail("unknown operator " + e.op);
      }
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
  } else {
    e.kind = Expr::OP; e.op = j.At("op").str;
    for (auto& a : j.At("args").arr) e.args.push_back(ReadExpr(a, vars));
    e.opcode = OpCode(e.op, e.args.size());
    if (e.opcode == Expr::UNKNOWN) Fail("unknown operator " + e.op);
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

struct KeyHash {
  size_t operator()(const std::vector<num>& k) const {
    uint64_t h = 1469598103934665603ULL;
    for (num x : k) { h ^= (uint64_t)(i64)x; h *= 1099511628211ULL; h ^= h >> 29; }
    return h;
  }
};

// ----------------------------------------------------------------------
// Aggregates of value columns.
enum Agg { MIN, MAX, ARGMIN, ARGMAX, SUM, ASSIGN };

Agg ParseAgg(const std::string& a) {
  if (a == "min") return MIN;
  if (a == "max") return MAX;
  if (a == "argmin") return ARGMIN;
  if (a == "argmax") return ARGMAX;
  if (a == "sum") return SUM;
  if (a == "assign") return ASSIGN;
  Fail("unknown aggregate " + a);
}

bool Lattice(Agg a) { return a == MIN || a == MAX || a == ARGMIN || a == ARGMAX; }

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
  enum Tier { LATTICE, GROUP, BLACKBOX } tier = BLACKBOX;
  bool has_arg = false;       // multi-column updates need a per-key lock
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

  void Init(i64 domain_lo, i64 domain_hi, int nthreads, bool lattice_opt, bool group_opt, bool computed_keys) {
    threads = nthreads;
    slots.nv = nv;
    argof.assign(nv, -1);
    for (int c = 0; c < nv; c++) {
      if (aggs[c] == ARGMIN || aggs[c] == ARGMAX) {
        has_arg = true;
        for (int d = c - 1; d >= 0; d--) if (aggs[d] == (aggs[c] == ARGMIN ? MIN : MAX)) { argof[c] = d; break; }
        if (argof[c] < 0) Fail("ArgMin/ArgMax column of " + name + " has no Min/Max column before it");
      }
    }
    bool lattice = true, group = nv > 0;
    for (Agg a : aggs) { lattice &= Lattice(a); group &= a == SUM; }
    tier = lattice && lattice_opt ? LATTICE : group && group_opt ? GROUP : BLACKBOX;
    delta.width = next_delta.width = DeltaWidth();
    spill.resize(threads); dirty_keys.resize(threads); dirty_overflow.resize(threads);
    i64 span = domain_hi - domain_lo + 1;
    if (computed_keys) span = 0;  // keys may be anything: generic storage
    if (arity == 1 && span > 0 && span < (i64)2000000000LL) {
      dense = true; lo = domain_lo; slots.Resize(span);
    } else if (arity == 2 && nv == 0 && span > 0 && span <= (1LL << 17) && span * span <= (1LL << 34)) {
      dense2 = true; lo = domain_lo; n2 = span;
      bits2.assign((size_t)((span * span + 63) / 64), 0);
    } else if (arity == 2 && domain_lo >= -(1LL << 31) && domain_hi < (1LL << 31)) {
      packed = true; pmap.Init(1 << 16); slots.Resize(1 << 16);
    }
  }

  static uint64_t PackKey(const num* row) { return ((uint64_t)(uint32_t)(i64)row[0] << 32) | (uint32_t)(i64)row[1]; }

  // Slot of a key, creating it (not alive) when absent; ~0 when the packed
  // probe limit is hit (the row is spilled). The generic path is only
  // used single-threaded.
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
          if (aggs[c] == SUM) { cur[c] += v[c]; changed |= v[c] != 0; }
          else if (aggs[c] == ASSIGN) { changed |= cur[c] != v[c]; cur[c] = v[c]; }
          else if (aggs[c] == MIN ? v[c] < cur[c] : v[c] > cur[c]) {
            cur[c] = v[c]; changed = true;
            for (int d = 0; d < nv; d++) if (argof[d] == c) cur[d] = v[d];
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
        case SUM: AtomicAdd(&cur[c], v[c]); changed |= v[c] != 0; break;
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

  // Marks a key for recomputation; each key is listed once per round
  // (a flag in its slot). Keys the packed table cannot place yet, and
  // generic keys, go to a list deduplicated at Pull time.
  std::vector<std::vector<num>> dirty_overflow;
  void MarkDirty(const num* keyrow) {
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
        if (Offer(&S[i])) { delta_out.insert(delta_out.end(), &S[i], &S[i] + arity); for (int c = 0; c < 2 * nv; c++) delta_out.push_back(0); }
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
  std::vector<int> preset;   // variables bound before the first atom
  int delta_pos = -1;        // execution position of the delta atom
};

struct Engine {
  int threads = 1;
  std::map<std::string, Rows> inputs;
  std::map<std::string, const Rows*> scan_rows;
  std::map<std::string, State> states;
  std::vector<Rule> rules;
  std::map<std::pair<std::string, std::vector<int>>, std::unique_ptr<Index>> input_index;
  std::map<std::string, Rows> full_state;  // materialized at round start
  std::map<std::pair<std::string, std::vector<int>>, std::unique_ptr<Index>> state_index;  // per round
  i64 domain_lo = 0, domain_hi = 0;
  double index_s = 0;
  bool trace = getenv("SOCRATES_TRACE") != nullptr;
  const size_t CHUNK = 1 << 18;

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
          if (j < hi && data[j] != ',' && data[j] != '\n' && data[j] != '\r') {
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
  Plan MakePlan(const Rule& rule, int delta_at, const std::vector<int>& preset) {
    Plan p; p.rule = &rule; p.preset = preset;
    int natoms = rule.atoms.size();
    for (int a = 0; a < natoms; a++) p.order.push_back(a);
    if (delta_at >= 0) { p.order.erase(p.order.begin() + delta_at); p.order.insert(p.order.begin(), delta_at); p.delta_pos = 0; }
    else if (!preset.empty()) {
      int best = -1;
      for (int a = 0; a < natoms; a++) {
        bool binds = false;
        for (auto& e : rule.atoms[a].args) if (e.kind == Expr::VAR) for (int v : preset) binds |= e.var == v;
        if (binds && (best < 0 || (rule.atoms[best].recursive && !rule.atoms[a].recursive))) best = a;
      }
      if (best > 0) { p.order.erase(p.order.begin() + best); p.order.insert(p.order.begin(), best); }
    }
    std::vector<char> is_bound(rule.nvars, 0);
    for (int v : preset) is_bound[v] = 1;
    p.src.resize(natoms); p.idx.assign(natoms, nullptr);
    p.bound_cols.resize(natoms); p.bind_cols.resize(natoms); p.const_cols.resize(natoms);
    p.conds_after.resize(natoms + 1); p.lets_after.resize(natoms + 1);
    auto resolve = [&](int stage) {
      bool changed = true;
      while (changed) {
        changed = false;
        for (size_t l = 0; l < rule.lets.size(); l++) {
          if (is_bound[rule.lets[l].first]) continue;
          std::vector<int> vs; ExprVars(rule.lets[l].second, vs);
          bool ok = true; for (int v : vs) if (!is_bound[v]) ok = false;
          if (ok) { is_bound[rule.lets[l].first] = 1; p.lets_after[stage].push_back(l); changed = true; }
        }
      }
      for (size_t c = 0; c < rule.conds.size(); c++) {
        bool placed = false;
        for (int s = 0; s < stage; s++) for (int x : p.conds_after[s]) if (x == (int)c) placed = true;
        if (placed) continue;
        std::vector<int> vs; ExprVars(rule.conds[c], vs);
        bool ok = true; for (int v : vs) if (!is_bound[v]) ok = false;
        if (ok) p.conds_after[stage].push_back(c);
      }
    };
    resolve(0);
    for (int pos = 0; pos < natoms; pos++) {
      int a = p.order[pos];
      const Atom& atom = rule.atoms[a];
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
      if (atom.recursive) {
        const Rows& rows = pos == p.delta_pos ? states.at(atom.rel).delta : full_state.at(atom.rel);
        p.src[pos] = &rows;
        if (lookup) p.idx[pos] = &StateIndex(atom.rel + (pos == p.delta_pos ? "#delta" : "#full"), index_cols, rows);
      } else {
        if (lookup) p.idx[pos] = &InputIndex(atom.rel, index_cols);
      }
      resolve(pos + 1);
    }
    for (int pos = 0; pos < natoms; pos++) {
      int a = p.order[pos];
      if (!rule.atoms[a].recursive) p.src[pos] = &InputRows(rule.atoms[a].rel);
    }
    // Scan order: a fully scanned first atom is read grouped by the column
    // later atoms look up through, so those lookups walk memory in order.
    if (!p.idx[0] && natoms > 1 && !rule.atoms[p.order[0]].recursive) {
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
    struct Frame { const Rows* rows; size_t r; size_t n; };
    std::vector<Frame> st(natoms);
    auto check_atom = [&](int pos, const num* row) -> bool {
      const Atom& atom = rule.atoms[p.order[pos]];
      for (int c : p.const_cols[pos]) if (row[c] != atom.args[c].value) return false;
      for (int c : p.bound_cols[pos]) if (row[c] != bind[atom.args[c].var]) return false;
      for (int c : p.bind_cols[pos]) bind[atom.args[c].var] = row[c];
      return true;
    };
    auto after = [&](int stage) -> bool {
      for (int l : p.lets_after[stage]) bind[rule.lets[l].first] = Eval(rule.lets[l].second, bind.data());
      for (int c : p.conds_after[stage]) if (!Eval(rule.conds[c], bind.data())) return false;
      return true;
    };
    auto open = [&](int pos) {
      Frame& f = st[pos];
      if (p.idx[pos]) {
        const Index& I = *p.idx[pos];
        for (size_t i = 0; i < I.cols.size(); i++) {
          const Expr& e = rule.atoms[p.order[pos]].args[I.cols[i]];
          probe[i] = e.kind == Expr::CONST ? e.value : bind[e.var];
        }
        I.Lookup(probe, &f.r, &f.n); f.rows = &I.sorted;
      } else {
        // Only the first atom is split into [r_begin, r_end) between
        // threads; a later atom without an index is scanned whole.
        f.rows = p.src[pos];
        f.r = pos == 0 ? r_begin : 0;
        f.n = pos == 0 ? r_end : p.src[pos]->size();
      }
    };
    auto next_row = [&](int pos) -> const num* {
      Frame& f = st[pos];
      if (f.r == f.n) return nullptr; return f.rows->row(f.r++);
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
      if (pos + 1 == natoms) emit(st[0].rows->row(st[0].r - 1));
      else { pos++; open(pos); }
    }
  }

  // Fast path for a linear monotone rule "delta, one input atom through a
  // CSR index", plain-variable head: the generic loop computes the same
  // thing at several times the cost per matched row.
  bool FastPush(const Plan& p, State& head, std::vector<Rows>& out) {
    const Rule& rule = *p.rule;
    if (rule.atoms.size() != 2 || p.delta_pos != 0 || !p.idx[1] || !p.idx[1]->csr) return false;
    if (!p.preset.empty() || !rule.conds.empty() || !rule.lets.empty()) return false;
    if (!p.const_cols[0].empty() || !p.const_cols[1].empty() || !p.bound_cols[0].empty() || p.bound_cols[1].size() != 1) return false;
    if (!(head.dense || head.dense2 || head.packed) || head.tier != State::LATTICE || head.has_arg) return false;
    int width = rule.keys.size() + rule.values.size();
    std::vector<std::pair<int, int>> head_src(width);
    for (int h = 0; h < width; h++) {
      const Expr& e = h < (int)rule.keys.size() ? rule.keys[h] : rule.values[h - rule.keys.size()];
      if (e.kind != Expr::VAR) return false;
      head_src[h] = {-1, -1};
      for (int c : p.bind_cols[0]) if (rule.atoms[p.order[0]].args[c].var == e.var) head_src[h] = {0, c};
      for (int c : p.bind_cols[1]) if (rule.atoms[p.order[1]].args[c].var == e.var) head_src[h] = {1, c};
      if (head_src[h].first < 0) return false;
    }
    int pcol = p.bound_cols[1][0];
    int pvar = rule.atoms[p.order[1]].args[pcol].var;
    int dcol = -1;
    for (int c : p.bind_cols[0]) if (rule.atoms[p.order[0]].args[c].var == pvar) dcol = c;
    if (dcol < 0) return false;
    const Rows& D = *p.src[0];
    const Index& I = *p.idx[1];
    const Rows& R1 = I.sorted;
    int w0 = D.width, w1 = R1.width;
    size_t n0 = D.size();
    for (size_t c0 = 0; c0 < n0; c0 += CHUNK) {
      size_t c1 = std::min(n0, c0 + CHUNK);
#pragma omp parallel num_threads(threads)
      {
        Rows& O = out[omp_get_thread_num()];
        num hrow[8];
#pragma omp for schedule(dynamic, 256)
        for (size_t r0 = c0; r0 < c1; r0++) {
          const num* row0 = D.data.data() + r0 * w0;
          i64 key = (i64)row0[dcol] - I.min_key;
          if (key < 0 || key + 1 >= (i64)I.offsets.size()) continue;
          size_t b = I.offsets[key], e = I.offsets[key + 1];
          for (; b != e; b++) {
            const num* row1 = R1.data.data() + b * w1;
            for (int h = 0; h < width; h++) hrow[h] = head_src[h].first == 0 ? row0[head_src[h].second] : row1[head_src[h].second];
            if (head.Offer(hrow)) O.push(hrow);
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
    if (FastPush(p, head, out)) return;
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
    if (head.tier == State::GROUP && delta_at >= 0) {
      const State& D = states.at(rule.atoms[delta_at].rel);
      darity = D.arity; dnv = D.nv;
      for (int c = 0; c < dnv; c++) {
        const Expr& e = (int)rule.atoms[delta_at].args.size() > darity + c ? rule.atoms[delta_at].args[darity + c] : Expr();
        dvars.push_back(e.kind == Expr::VAR ? e.var : -1);
      }
    }
    size_t n0 = p.src[0]->size();
    int nthreads = (head.dense || head.dense2 || head.packed) ? threads : 1;
    for (size_t c0 = 0; c0 < n0; c0 += CHUNK) {
      size_t c1 = std::min(n0, c0 + CHUNK);
#pragma omp parallel num_threads(nthreads)
      {
        std::vector<num> bind(rule.nvars, 0);
        std::vector<num> hrow(width);
        Rows& O = out[omp_get_thread_num()];
        size_t per = (c1 - c0 + nthreads - 1) / nthreads;
        size_t lo = c0 + per * omp_get_thread_num(), hi = std::min(c1, lo + per);
        auto head_row = [&]() {
          for (size_t k = 0; k < rule.keys.size(); k++) hrow[k] = Eval(rule.keys[k], bind.data());
          for (size_t v = 0; v < rule.values.size(); v++) hrow[rule.keys.size() + v] = Eval(rule.values[v], bind.data());
        };
        if (lo < hi) RunPlan(p, lo, hi, bind, [&](const num* row0) {
          head_row();
          if (trace && n0 < 4) fprintf(stderr, "    emit %s value %g (delta row0 %g)\n", rule.head.c_str(), width ? hrow[0] : 0, row0 ? row0[0] : -1);
          if (head.Offer(hrow.data())) O.push(hrow.data());
          if (dnv && !std::isnan(row0[darity + dnv])) {
            num saved[8];
            for (int c = 0; c < dnv; c++) if (dvars[c] >= 0) { saved[c] = bind[dvars[c]]; bind[dvars[c]] = row0[darity + dnv + c]; }
            head_row();
            for (size_t v = 0; v < rule.values.size(); v++) hrow[rule.keys.size() + v] = -hrow[rule.keys.size() + v];
            if (head.Offer(hrow.data())) O.push(hrow.data());
            for (int c = 0; c < dnv; c++) if (dvars[c] >= 0) bind[dvars[c]] = saved[c];
          }
        });
      }
      head.Maintain(out[0].data);
    }
  }

  // Affected keys: every match marks its head key dirty.
  void MarkAffected(const Rule& rule, int delta_at) {
    State& head = states.at(rule.head);
    Plan p = MakePlan(rule, delta_at, {});
    size_t n0 = p.src[0]->size();
#pragma omp parallel num_threads(threads)
    {
      std::vector<num> bind(rule.nvars, 0);
      std::vector<num> krow(rule.keys.size());
      size_t per = (n0 + threads - 1) / threads;
      size_t lo = per * omp_get_thread_num(), hi = std::min(n0, lo + per);
      if (lo < hi) RunPlan(p, lo, hi, bind, [&](const num*) {
        for (size_t k = 0; k < rule.keys.size(); k++) krow[k] = Eval(rule.keys[k], bind.data());
        head.MarkDirty(krow.data());
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
    if (dirty.empty()) return;
    struct Pending { const Rule* rule; Plan plan; std::vector<int> key_vars; };
    std::vector<Pending> plans;  // built serially: indexes are shared
    for (auto& rule : rules) {
      if (rule.head != S.name) continue;
      std::vector<int> key_vars;
      for (auto& k : rule.keys) { if (k.kind != Expr::VAR) Fail("recomputation needs plain head keys in " + S.name); key_vars.push_back(k.var); }
      plans.push_back({&rule, MakePlan(rule, -1, key_vars), key_vars});
    }
    for (auto& o : out) o.width = S.DeltaWidth();
    if (S.packed) {
      size_t need = S.pmap.count + dirty.size();
      size_t cap = S.pmap.keys.size();
      while (need * 2 > cap) cap <<= 1;
      if (cap != S.pmap.keys.size()) S.Rehash(cap);
    }
    bool generic = !S.dense && !S.packed;
#pragma omp parallel num_threads(generic ? 1 : threads)
    {
      Rows& O = out[omp_get_thread_num()];
      std::vector<num> acc(S.nv), contrib(S.nv);
      std::vector<std::vector<num>> binds;
      for (auto& pd : plans) binds.emplace_back(pd.rule->nvars, 0);
#pragma omp for schedule(dynamic, 64)
      for (size_t i = 0; i < dirty.size(); i++) {
        const std::vector<num>& key = dirty[i];
        bool any = false;
        for (size_t pi = 0; pi < plans.size(); pi++) {
          Pending& pd = plans[pi];
          const Rule& rule = *pd.rule;
          std::vector<num>& bind = binds[pi];
          for (size_t k = 0; k < pd.key_vars.size(); k++) bind[pd.key_vars[k]] = key[k];
          RunPlan(pd.plan, 0, rule.atoms.empty() ? 0 : pd.plan.src[0]->size(), bind, [&](const num*) {
            for (int c = 0; c < S.nv; c++) contrib[c] = Eval(rule.values[c], bind.data());
            if (!any) { acc = contrib; any = true; return; }
            for (int c = 0; c < S.nv; c++) {
              switch (S.aggs[c]) {
                case SUM: acc[c] += contrib[c]; break;
                case ASSIGN: acc[c] = contrib[c]; break;
                case MIN: case MAX:
                  if (S.aggs[c] == MIN ? contrib[c] < acc[c] : contrib[c] > acc[c]) {
                    acc[c] = contrib[c];
                    for (int d = 0; d < S.nv; d++) if (S.argof[d] == c) acc[d] = contrib[d];
                  }
                  break;
                default: break;
              }
            }
          });
        }
        if (S.Set(key.data(), any ? acc.data() : nullptr)) {
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

  // ----------------------------------------------------------------- run
  std::string Run(const Json& spec) {
    threads = spec.Get("threads") ? (int)spec.At("threads").num : omp_get_max_threads();
    omp_set_num_threads(threads);
    int max_rounds = spec.Get("max_rounds") ? (int)spec.At("max_rounds").num : 1000000000;
    num eps = spec.Get("epsilon") ? spec.At("epsilon").num : 1e-12;
    double t0 = Now();
    bool any = false;
    for (auto& kv : spec.At("relations").obj) {
      const Json& r = kv.second;
      int arity = (int)r.At("arity").num;
      if (r.At("kind").str == "input") {
        int nv = r.Get("values") ? (int)r.At("values").num : (r.Get("value") && r.At("value").b ? 1 : 0);
        Rows R = ReadCsv(r.At("file").str, arity + nv);
        for (size_t i = 0; i < R.size(); i++) for (int c = 0; c < arity; c++) {
          i64 x = (i64)R.row(i)[c];
          if (!any || x < domain_lo) domain_lo = x;
          if (!any || x > domain_hi) domain_hi = x;
          any = true;
        }
        inputs[kv.first] = std::move(R);
      } else {
        State S; S.name = kv.first; S.arity = arity; S.eps = eps;
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
        atom.recursive = states.count(atom.rel) > 0;
        atom.has_value = aj.Get("has_value") && aj.At("has_value").b;
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
    auto flag = [](const char* name) { const char* v = getenv(name); return !(v && (!strcmp(v, "false") || !strcmp(v, "0"))); };
    bool lattice_opt = flag("SOCRATIC_LATTICE_OPT"), group_opt = flag("SOCRATIC_GROUP_OPT");
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
    for (auto& kv : states) kv.second.Init(domain_lo, domain_hi, threads, lattice_opt, group_opt, computed_keys.count(kv.first) > 0);
    // States read in full each round: by a non-linear rule, or by the
    // recomputation of a black-box head.
    std::set<std::string> needs_full;
    for (auto& rule : rules) {
      int nrec = 0; for (auto& a : rule.atoms) nrec += a.recursive;
      if (nrec > 1 || states.at(rule.head).tier == State::BLACKBOX) for (auto& a : rule.atoms) if (a.recursive) needs_full.insert(a.rel);
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
    while (rounds < max_rounds) {
      rounds++;
      double tr = Now();
      bool progress = false;
      for (State* member : members) {
        State& S = *member;
        S.Snapshot();
        state_index.clear();
        full_state.clear();
        for (auto& name : needs_full) full_state[name] = states.at(name).Materialize();
        for (const Rule* rule : rules_of[S.name]) {
          bool rec = false; for (auto& a : rule->atoms) rec |= a.recursive;
          if (!rec) {
            if (rounds == 1) { Push(*rule, -1, out); Collect(S, out); }
            continue;
          }
          for (size_t a = 0; a < rule->atoms.size(); a++) {
            if (!rule->atoms[a].recursive) continue;
            State& B = states.at(rule->atoms[a].rel);
            size_t from = cursor[rule][a], to = B.log.size();
            cursor[rule][a] = to;
            if (from == to) continue;
            B.delta.width = B.log.width;
            B.delta.data.assign(B.log.data.begin() + from * B.log.width, B.log.data.begin() + to * B.log.width);
            for (auto& kv : state_index) {} state_index.erase(std::make_pair(B.name + "#delta", std::vector<int>{0}));
            for (auto it = state_index.begin(); it != state_index.end();) { if (it->first.first == B.name + "#delta") it = state_index.erase(it); else ++it; }
            if (trace) fprintf(stderr, "  %s <- %s: %zu changed rows\n", rule->head.c_str(), B.name.c_str(), to - from);
            if (S.tier != State::BLACKBOX) { Push(*rule, a, out); Collect(S, out); }
            else MarkAffected(*rule, a);
          }
        }
        if (S.tier == State::BLACKBOX) Pull(S, out);
        size_t before = S.log.size();
        size_t pending = S.next_delta.size();
        S.CloseRound();
        if (trace) fprintf(stderr, "  %s: %zu queued, %zu logged\n", S.name.c_str(), pending, S.log.size() - before);
        if (S.log.size() > before) progress = true;
      }
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
      if (trace) fprintf(stderr, "pass %d %.3f s\n", rounds, Now() - tr);
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
      Rows R = S.Materialize();
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
          for (int c = 0; c < R.width; c++) {
            num x = row[c];
            char end = c + 1 == R.width ? '\n' : ',';
            if (x == (num)(i64)x && x > -9e15 && x < 9e15) {
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
      stats += ", \"" + kv.first + "\": " + std::to_string(R.size());
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

extern "C" {
int socrates_run(const char* spec_json, char* out, int out_len) {
  signal(SIGSEGV, OnCrash); signal(SIGBUS, OnCrash); signal(SIGABRT, OnCrash);
  JsonParser p(spec_json);
  Json spec = p.Parse();
  Engine engine;
  std::string stats = engine.Run(spec);
  snprintf(out, out_len, "%s", stats.c_str());
  return 0;
}
}

#ifndef SOCRATES_LIBRARY
int main(int argc, char** argv) {
  if (argc < 2) { fprintf(stderr, "usage: socrates spec.json\n"); return 1; }
  FILE* f = fopen(argv[1], "r"); if (!f) { perror("spec"); return 1; }
  std::string text; char buf[65536]; size_t n;
  while ((n = fread(buf, 1, sizeof buf, f)) > 0) text.append(buf, n);
  fclose(f);
  char out[65536];
  socrates_run(text.c_str(), out, sizeof out);
  printf("%s\n", out);
  return 0;
}
#endif
