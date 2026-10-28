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
// Composite values of the Socrates engine: arrays and records.
//
// A row holds only numbers. A string is its id in the dictionary (shared
// with the SQL side); an array or a record is its id in the arena, a
// store that interns every composite value once, so that equal values
// have equal ids and a composite can be a key. The arena only grows.
//
// Values cross to SQL as JSON, guided by the column's type (the engine
// cannot tell a string id from a number by itself).

#ifndef SOCRATES_VALUES_H
#define SOCRATES_VALUES_H

#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

typedef double num;
const num NONE = std::numeric_limits<num>::quiet_NaN();

inline uint64_t Bits(num x) {
  if (std::isnan(x)) x = NONE;  // one null
  uint64_t b; memcpy(&b, &x, 8); return b;
}

// Strings: id -> text, ids given by the SQL side (1-based); strings met
// inside composite inputs get the next ids and are reported back.
struct Dictionary {
  std::vector<std::string> text;  // index = id
  std::unordered_map<std::string, int> id;
  int given = 0;  // ids up to this one came from SQL
  int Intern(const std::string& s) {
    auto it = id.find(s);
    if (it != id.end()) return it->second;
    if (text.empty()) text.push_back("");
    int i = text.size();
    text.push_back(s); id[s] = i;
    return i;
  }
  const std::string& Text(num x) const {
    size_t i = (size_t)(int64_t)x;
    static const std::string none;
    return i < text.size() ? text[i] : none;
  }
};

// Arrays and records. A record's elements are (field id, value) pairs
// sorted by field id, so that equal records intern to one node.
struct Arena {
  enum Kind { ARRAY = 0, RECORD = 1 };
  std::vector<num> data;
  std::vector<size_t> start;  // node i: data[start[i], start[i+1])
  std::vector<uint8_t> kind;
  std::unordered_map<uint64_t, std::vector<uint32_t>> buckets;

  size_t Count() const { return kind.size(); }
  bool Valid(num x) const { return !std::isnan(x) && x >= 0 && x < (num)kind.size() && x == (num)(int64_t)x; }
  size_t Size(num x) const { size_t i = (size_t)x; return start[i + 1] - start[i]; }
  const num* Elems(num x) const { return data.data() + start[(size_t)x]; }
  Kind KindOf(num x) const { return (Kind)kind[(size_t)x]; }

  static uint64_t Hash(Kind k, const num* e, size_t n) {
    uint64_t h = 1469598103934665603ULL ^ (uint64_t)k;
    for (size_t i = 0; i < n; i++) { h ^= Bits(e[i]); h *= 1099511628211ULL; h ^= h >> 29; }
    return h;
  }
  num Make(Kind k, const num* e, size_t n) {
    uint64_t h = Hash(k, e, n);
    std::vector<uint32_t>& b = buckets[h];
    for (uint32_t i : b) {
      if (kind[i] != k || Size(i) != n) continue;
      bool same = true;
      const num* f = Elems(i);
      for (size_t j = 0; j < n && same; j++) same = Bits(e[j]) == Bits(f[j]);
      if (same) return i;
    }
    if (start.empty()) start.push_back(0);
    uint32_t i = kind.size();
    data.insert(data.end(), e, e + n);
    start.push_back(data.size());
    kind.push_back(k);
    b.push_back(i);
    return i;
  }
  num MakeArray(const num* e, size_t n) { return Make(ARRAY, e, n); }
  // Pairs (field id, value), any order.
  num MakeRecord(std::vector<std::pair<num, num>> fields) {
    std::sort(fields.begin(), fields.end(), [](const std::pair<num, num>& a, const std::pair<num, num>& b) { return a.first < b.first; });
    std::vector<num> e;
    for (auto& f : fields) { e.push_back(f.first); e.push_back(f.second); }
    return Make(RECORD, e.data(), e.size());
  }
  num Field(num r, num field) const {
    if (!Valid(r) || KindOf(r) != RECORD) return NONE;
    const num* e = Elems(r); size_t n = Size(r);
    for (size_t i = 0; i < n; i += 2) if (e[i] == field) return e[i + 1];
    return NONE;
  }
};

// The type of a column, from the compiler, as far as it knows it.
struct Type {
  enum Kind { NUM, STR, ANY, ARRAY, RECORD } kind = ANY;
  std::vector<std::pair<std::string, Type>> fields;  // RECORD
  std::vector<Type> elem;                            // ARRAY: one
  bool Composite() const { return kind == ARRAY || kind == RECORD; }
};

// JSON text of a value of the given type; strings and field names from
// the dictionary.
inline void FormatNumber(num x, std::string& out) {
  char buf[40];
  if (x == (num)(int64_t)x && x > -9e15 && x < 9e15) snprintf(buf, sizeof buf, "%lld", (long long)x);
  else snprintf(buf, sizeof buf, "%.17g", x);
  out += buf;
}
inline void QuoteJson(const std::string& s, std::string& out) {
  out += '"';
  for (char c : s) {
    if (c == '"' || c == '\\') { out += '\\'; out += c; }
    else if (c == '\n') out += "\\n";
    else if (c == '\t') out += "\\t";
    else if (c == '\r') out += "\\r";
    else out += c;
  }
  out += '"';
}
inline void ToJson(num x, const Type& t, const Arena& arena, const Dictionary& dict, std::string& out) {
  if (std::isnan(x)) { out += "null"; return; }
  switch (t.kind) {
    case Type::STR: QuoteJson(dict.Text(x), out); return;
    case Type::ARRAY: {
      if (!arena.Valid(x)) { out += "null"; return; }
      out += '[';
      const num* e = arena.Elems(x); size_t n = arena.Size(x);
      for (size_t i = 0; i < n; i++) { if (i) out += ','; ToJson(e[i], t.elem.empty() ? Type() : t.elem[0], arena, dict, out); }
      out += ']';
      return;
    }
    case Type::RECORD: {
      if (!arena.Valid(x)) { out += "null"; return; }
      out += '{';
      bool first = true;
      for (auto& f : t.fields) {
        auto it = dict.id.find(f.first);
        num v = it == dict.id.end() ? NONE : arena.Field(x, it->second);
        if (!first) out += ','; first = false;
        QuoteJson(f.first, out); out += ':';
        ToJson(v, f.second, arena, dict, out);
      }
      out += '}';
      return;
    }
    default:
      if (arena.Valid(x) && t.kind == Type::ANY && false) {}
      FormatNumber(x, out);
  }
}

// JSON text -> value of the given type (strings interned, composites
// made in the arena). Lenient: anything unexpected becomes null.
struct JsonReader {
  const char* s; size_t i = 0;
  Arena& arena; Dictionary& dict;
  JsonReader(const char* text, Arena& a, Dictionary& d) : s(text), arena(a), dict(d) {}
  void Ws() { while (s[i] == ' ' || s[i] == '\n' || s[i] == '\t' || s[i] == '\r') i++; }
  std::string String() {
    std::string r; i++;  // opening quote
    while (s[i] && s[i] != '"') {
      if (s[i] == '\\') { i++; char c = s[i++]; r += c == 'n' ? '\n' : c == 't' ? '\t' : c == 'r' ? '\r' : c; }
      else r += s[i++];
    }
    if (s[i] == '"') i++;
    return r;
  }
  void Skip() {  // any value
    Ws();
    if (s[i] == '"') { String(); return; }
    if (s[i] == '[' || s[i] == '{') { char close = s[i] == '[' ? ']' : '}'; i++; Ws(); while (s[i] && s[i] != close) { Skip(); Ws(); if (s[i] == ',' || s[i] == ':') i++; Ws(); } if (s[i]) i++; return; }
    while (s[i] && s[i] != ',' && s[i] != ']' && s[i] != '}') i++;
  }
  num Value(const Type& t) {
    Ws();
    if (!strncmp(s + i, "null", 4)) { i += 4; return NONE; }
    if (s[i] == '"') { std::string str = String(); if (t.kind == Type::NUM) return strtod(str.c_str(), nullptr); return dict.Intern(str); }
    if (s[i] == '[') {
      i++; std::vector<num> e; Type et = t.elem.empty() ? Type() : t.elem[0];
      Ws();
      while (s[i] && s[i] != ']') { e.push_back(Value(et)); Ws(); if (s[i] == ',') i++; Ws(); }
      if (s[i]) i++;
      return arena.MakeArray(e.data(), e.size());
    }
    if (s[i] == '{') {
      i++; std::vector<std::pair<num, num>> f;
      Ws();
      while (s[i] && s[i] != '}') {
        std::string name = s[i] == '"' ? String() : "";
        Ws(); if (s[i] == ':') i++;
        const Type* ft = nullptr;
        for (auto& p : t.fields) if (p.first == name) ft = &p.second;
        f.emplace_back(dict.Intern(name), Value(ft ? *ft : Type()));
        Ws(); if (s[i] == ',') i++; Ws();
      }
      if (s[i]) i++;
      return arena.MakeRecord(f);
    }
    if (!strncmp(s + i, "true", 4)) { i += 4; return 1; }
    if (!strncmp(s + i, "false", 5)) { i += 5; return 0; }
    char* e; num v = strtod(s + i, &e);
    if (e == s + i) { Skip(); return NONE; }
    i = e - s;
    return v;
  }
};

}  // namespace

#endif  // SOCRATES_VALUES_H
