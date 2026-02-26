// Copyright 2026 The Logica Authors
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

// Standalone C++ port of Logica parser (parser_py/parse.py)
//
// Build:
//   g++ -std=c++20 -O2 -Wall -Wextra -pedantic -o logica_parse_cpp parser_cpp/logica_parse.cpp
//
// Run:
//   ./logica_parse_cpp program.l
//   cat program.l | ./logica_parse_cpp -
//
// Notes:
// - Outputs JSON (sorted keys) similar to `python3 logica.py <file> parse`.
// - This is a direct functional port of the Python parser; it does not depend on
//   the rest of Logica compiler.

#include <algorithm>
#include <cctype>
#include <cerrno>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <variant>
#include <vector>
#include <cstring>

namespace logica::parser {

// ------------------------------
// Minimal JSON value.
// ------------------------------

struct Json;
using JsonObject = std::map<std::string, Json>;
using JsonArray = std::vector<Json>;

struct Json {
  using Storage = std::variant<std::nullptr_t, bool, int64_t, std::string, JsonArray, JsonObject>;
  Storage v;

  Json() : v(nullptr) {}
  Json(std::nullptr_t) : v(nullptr) {}
  Json(bool b) : v(b) {}
  Json(int64_t n) : v(n) {}
  Json(int n) : v(static_cast<int64_t>(n)) {}
  Json(std::string s) : v(std::move(s)) {}
  Json(const char* s) : v(std::string(s)) {}
  Json(JsonArray a) : v(std::move(a)) {}
  Json(JsonObject o) : v(std::move(o)) {}

  bool is_null() const { return std::holds_alternative<std::nullptr_t>(v); }
  bool is_bool() const { return std::holds_alternative<bool>(v); }
  bool is_int() const { return std::holds_alternative<int64_t>(v); }
  bool is_string() const { return std::holds_alternative<std::string>(v); }
  bool is_array() const { return std::holds_alternative<JsonArray>(v); }
  bool is_object() const { return std::holds_alternative<JsonObject>(v); }

  const std::string& as_string() const { return std::get<std::string>(v); }
  int64_t as_int() const { return std::get<int64_t>(v); }
  const JsonArray& as_array() const { return std::get<JsonArray>(v); }
  const JsonObject& as_object() const { return std::get<JsonObject>(v); }
  JsonArray& as_array() { return std::get<JsonArray>(v); }
  JsonObject& as_object() { return std::get<JsonObject>(v); }

  static std::string Escape(std::string_view s) {
    std::string out;
    out.reserve(s.size() + 4);
    for (char c : s) {
      switch (c) {
        case '\\': out += "\\\\"; break;
        case '"': out += "\\\""; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        default:
          if (static_cast<unsigned char>(c) < 0x20) {
            std::ostringstream oss;
            oss << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                << static_cast<int>(static_cast<unsigned char>(c));
            out += oss.str();
          } else {
            out += c;
          }
      }
    }
    return out;
  }

  void Dump(std::ostream& os, bool pretty, int indent, int depth) const {
    const auto pad = [&](int d) {
      if (!pretty) return;
      for (int i = 0; i < d * indent; ++i) os.put(' ');
    };

    if (is_null()) {
      os << "null";
    } else if (is_bool()) {
      os << (std::get<bool>(v) ? "true" : "false");
    } else if (is_int()) {
      os << std::get<int64_t>(v);
    } else if (is_string()) {
      os << '"' << Escape(std::get<std::string>(v)) << '"';
    } else if (is_array()) {
      const auto& a = std::get<JsonArray>(v);
      os << '[';
      if (!a.empty()) {
        if (pretty) os << '\n';
        for (size_t i = 0; i < a.size(); ++i) {
          pad(depth + 1);
          a[i].Dump(os, pretty, indent, depth + 1);
          if (i + 1 < a.size()) os << ',';
          if (pretty) os << '\n';
        }
        pad(depth);
      }
      os << ']';
    } else {
      const auto& o = std::get<JsonObject>(v);
      os << '{';
      if (!o.empty()) {
        if (pretty) os << '\n';
        size_t i = 0;
        for (const auto& [k, val] : o) {
          pad(depth + 1);
          os << '"' << Escape(k) << '"' << ':';
          if (pretty) os << ' ';
          val.Dump(os, pretty, indent, depth + 1);
          if (++i < o.size()) os << ',';
          if (pretty) os << '\n';
        }
        pad(depth);
      }
      os << '}';
    }
  }

  std::string ToString(bool pretty = true, int indent = 1) const {
    std::ostringstream oss;
    Dump(oss, pretty, indent, 0);
    return oss.str();
  }
};

// ------------------------------
// Heritage-aware string (SpanString).
// ------------------------------

struct SpanString {
  std::shared_ptr<std::string> heritage;
  size_t start = 0;
  size_t stop = 0;  // exclusive

  SpanString() : heritage(std::make_shared<std::string>()), start(0), stop(0) {}
  explicit SpanString(std::string s)
      : heritage(std::make_shared<std::string>(std::move(s))), start(0), stop(heritage->size()) {}

  SpanString(std::shared_ptr<std::string> h, size_t s, size_t e)
      : heritage(std::move(h)), start(s), stop(e) {
    if (stop > heritage->size()) stop = heritage->size();
    if (start > stop) start = stop;
  }

  size_t size() const { return stop - start; }
  bool empty() const { return size() == 0; }

  std::string_view view() const {
    return std::string_view(*heritage).substr(start, stop - start);
  }

  std::string str() const { return std::string(view()); }

  char at(size_t i) const { return (*heritage)[start + i]; }

  SpanString slice(size_t rel_start, size_t rel_stop) const {
    size_t s = start + rel_start;
    size_t e = start + rel_stop;
    return SpanString(heritage, s, e);
  }

  SpanString slice_from(size_t rel_start) const { return slice(rel_start, size()); }
  SpanString slice_to(size_t rel_stop) const { return slice(0, rel_stop); }

  bool starts_with(std::string_view p) const {
    auto v = view();
    return v.size() >= p.size() && v.substr(0, p.size()) == p;
  }

  bool ends_with(std::string_view sfx) const {
    auto v = view();
    return v.size() >= sfx.size() && v.substr(v.size() - sfx.size()) == sfx;
  }

  std::tuple<std::string, std::string, std::string> Pieces() const {
    std::string before = heritage->substr(0, start);
    std::string mid = heritage->substr(start, stop - start);
    std::string after = heritage->substr(stop);
    return {before, mid, after};
  }
};

// ------------------------------
// Parsing exception.
// ------------------------------

struct ParsingException : public std::runtime_error {
  SpanString location;

  ParsingException(const std::string& message, SpanString loc)
      : std::runtime_error(message), location(std::move(loc)) {}

  void ShowMessage(std::ostream& os = std::cerr) const {
    // Match python parser_py/parse.py::ParsingException.ShowMessage().
    constexpr const char* kErr = "\033[91m";
    constexpr const char* kWarn = "\033[1m";
    constexpr const char* kUnderline = "\033[4m";
    constexpr const char* kEnd = "\033[0m";

    os << kUnderline << "Parsing" << kEnd << ":\n";
    auto [before, mid, after] = location.Pieces();
    if (before.size() > 300) before = before.substr(before.size() - 300);
    if (after.size() > 300) after = after.substr(0, 300);
    if (mid.empty()) mid = "<EMPTY>";

    os << before << kWarn << mid << kEnd << after << "\n";

    std::string msg = what();
    // Support python-style markup >>...<< in messages.
    for (size_t pos = 0; (pos = msg.find(">>", pos)) != std::string::npos;) {
      msg.replace(pos, 2, kWarn);
      pos += std::strlen(kWarn);
    }
    for (size_t pos = 0; (pos = msg.find("<<", pos)) != std::string::npos;) {
      msg.replace(pos, 2, kEnd);
      pos += std::strlen(kEnd);
    }

    os << "\n[ " << kErr << "Error" << kEnd << " ] " << msg << "\n";
  }
};

// ------------------------------
// Traverse implementation.
// ------------------------------

static const std::map<char, char> kCloseToOpen = {
    {')', '('},
    {'}', '{'},
    {']', '['},
};

enum class TraverseStatus {
  OK,
  Unmatched,
  EolInString,
};

struct TraverseStep {
  size_t idx = 0;            // relative to current SpanString
  std::string state;         // internal state stack
  TraverseStatus status = TraverseStatus::OK;
};

struct Traverser {
  SpanString s;
  long idx = -1;
  std::string state;

  explicit Traverser(SpanString ss) : s(std::move(ss)) {}

  char State() const {
    if (state.empty()) return '\0';
    return state.back();
  }

  bool Next(TraverseStep& out) {
    if (static_cast<size_t>(idx + 1) >= s.size()) {
      return false;
    }
    idx += 1;
    const char c = s.at(static_cast<size_t>(idx));
    const std::string_view v = s.view();
    const auto sub2 = [&](size_t i) -> std::string_view {
      if (i + 2 > v.size()) return std::string_view();
      return v.substr(i, 2);
    };
    const auto sub3 = [&](size_t i) -> std::string_view {
      if (i + 3 > v.size()) return std::string_view();
      return v.substr(i, 3);
    };

    bool track_parenthesis = true;
    const char st = State();

    if (st == '#') {
      track_parenthesis = false;
      if (c == '\n') {
        state.pop_back();
      } else {
        // Comment chars are invisible.
        return Next(out);
      }
    } else if (st == '"') {
      track_parenthesis = false;
      if (c == '\n') {
        out = {static_cast<size_t>(idx), std::string(), TraverseStatus::EolInString};
        return true;
      }
      if (c == '"') {
        state.pop_back();
      }
    } else if (st == '\'') {
      track_parenthesis = false;
      if (c == '\'') {
        state.pop_back();
      }
      if (c == '\\') {
        state.push_back('\\');
      }
    } else if (st == '\\') {
      // character is screened whatever that is.
      state.pop_back();
    } else if (st == '`') {
      track_parenthesis = false;
      if (c == '`') {
        state.pop_back();
      }
    } else if (st == '3') {
      track_parenthesis = false;
      if (sub3(static_cast<size_t>(idx)) == "\"\"\"") {
        state.pop_back();
        // yield for current idx and the next two indices, like python.
        out = {static_cast<size_t>(idx), state, TraverseStatus::OK};
        // We will set up internal idx increments by manually bumping idx here,
        // but we must yield each char. We'll mimic python by returning one step
        // at a time: set a special mechanism to emit the next two chars.
        // Simplest: store a pending counter in state using a sentinel.
        // Instead, we do a mini state machine by injecting '\x01' twice.
        state.push_back('\x01');
        state.push_back('\x01');
        return true;
      }
    } else if (st == '/') {
      track_parenthesis = false;
      if (sub2(static_cast<size_t>(idx)) == "*/") {
        state.pop_back();
        idx += 1;  // consume '/'
      }
      // Comment chars are invisible.
      return Next(out);
    } else if (st == '\x01') {
      // Pending extra yields after closing triple quotes.
      track_parenthesis = false;
      state.pop_back();
      out = {static_cast<size_t>(idx), state, TraverseStatus::OK};
      return true;
    } else {
      // Not in comment nor string.
      if (c == '#') {
        state.push_back('#');
        return Next(out);
      }
      if (sub3(static_cast<size_t>(idx)) == "\"\"\"") {
        state.push_back('3');
        out = {static_cast<size_t>(idx), state, TraverseStatus::OK};
        // mimic python: yield next two quotes as well
        state.push_back('\x01');
        state.push_back('\x01');
        return true;
      }
      if (c == '"') {
        state.push_back('"');
      } else if (c == '\'') {
        state.push_back('\'');
      } else if (c == '`') {
        state.push_back('`');
      } else if (sub2(static_cast<size_t>(idx)) == "/*") {
        state.push_back('/');
        idx += 1;  // consume '*'
        return Next(out);
      }
    }

    if (track_parenthesis) {
      if (c == '(' || c == '{' || c == '[') {
        state.push_back(c);
      } else if (c == ')' || c == '}' || c == ']') {
        auto it = kCloseToOpen.find(c);
        if (it != kCloseToOpen.end()) {
          if (!state.empty() && state.back() == it->second) {
            state.pop_back();
          } else {
            out = {static_cast<size_t>(idx), std::string(), TraverseStatus::Unmatched};
            return true;
          }
        }
      }
    }

    out = {static_cast<size_t>(idx), state, TraverseStatus::OK};
    return true;
  }
};

static std::string RemoveComments(const SpanString& s) {
  std::string chars;
  chars.reserve(s.size());
  Traverser t(s);
  TraverseStep step;
  while (t.Next(step)) {
    if (step.status == TraverseStatus::Unmatched) {
      throw ParsingException("Parenthesis matches nothing.", s.slice(step.idx, step.idx + 1));
    }
    if (step.status == TraverseStatus::EolInString) {
      throw ParsingException("End of line in string.", s.slice(step.idx, step.idx));
    }
    chars.push_back(s.at(step.idx));
  }
  return chars;
}

static bool IsWhole(const SpanString& s) {
  Traverser t(s);
  TraverseStep step;
  TraverseStatus status = TraverseStatus::OK;
  std::string st;
  while (t.Next(step)) {
    status = step.status;
    st = step.state;
  }
  return status == TraverseStatus::OK && st.empty();
}

static SpanString StripSpaces(const SpanString& s) {
  auto v = s.view();
  size_t left = 0;
  size_t right = v.empty() ? 0 : v.size() - 1;
  while (left < v.size() && std::isspace(static_cast<unsigned char>(v[left]))) left++;
  if (v.empty()) return s.slice(0, 0);
  while (right > left && std::isspace(static_cast<unsigned char>(v[right]))) right--;
  return s.slice(left, right + 1);
}

static SpanString Strip(const SpanString& input) {
  SpanString s = input;
  while (true) {
    s = StripSpaces(s);
    if (s.size() >= 2 && s.at(0) == '(' && s.at(s.size() - 1) == ')' && IsWhole(s.slice(1, s.size() - 1))) {
      s = s.slice(1, s.size() - 1);
    } else {
      return s;
    }
  }
}

static std::vector<SpanString> SplitRaw(const SpanString& s, std::string_view separator) {
  std::vector<SpanString> parts;
  const size_t l = separator.size();
  if (l == 0) {
    parts.push_back(s);
    return parts;
  }

  Traverser t(s);
  TraverseStep step;
  size_t part_start = 0;
  const bool sep_alphanum = std::all_of(separator.begin(), separator.end(), [](char c) {
    return std::isalnum(static_cast<unsigned char>(c));
  });

  while (t.Next(step)) {
    if (step.status != TraverseStatus::OK) {
      throw ParsingException("Parenthesis matches nothing.", s.slice(step.idx, step.idx + 1));
    }
    if (!step.state.empty()) continue;

    auto v = s.view();
    const size_t i = step.idx;
    if (i + l <= v.size() && v.substr(i, l) == separator) {
      // hack to avoid parsing || as two |
      if (l == 1 && separator[0] == '|' && i + 1 < v.size() && v[i + 1] == '|') {
        continue;
      }
      if (l == 1 && separator[0] == '|' && i > 0 && v[i - 1] == '|') {
        continue;
      }

      // Bail out if this is alphanum separator that's part of a word.
      if (sep_alphanum) {
        bool left_ok = !(i > 0 && std::isalnum(static_cast<unsigned char>(v[i - 1])));
        bool right_ok = !((i + l) < v.size() && std::isalnum(static_cast<unsigned char>(v[i + l])));
        if (!left_ok || !right_ok) {
          continue;
        }
      }

      parts.push_back(s.slice(part_start, i));
      // Skip separator length - 1 characters.
      for (size_t k = 0; k + 1 < l; ++k) {
        if (!t.Next(step)) break;
      }
      part_start = i + l;
    }
  }

  parts.push_back(s.slice(part_start, s.size()));
  return parts;
}

static std::vector<SpanString> Split(const SpanString& s, std::string_view separator) {
  auto raw = SplitRaw(s, separator);
  for (auto& p : raw) {
    p = Strip(p);
  }
  return raw;
}

static std::pair<SpanString, SpanString> SplitInTwo(const SpanString& s, std::string_view separator) {
  auto parts = Split(s, separator);
  if (parts.size() != 2) {
    throw ParsingException(std::string("I expected string to be split by ") + std::string(separator) + " in two.", s);
  }
  return {parts[0], parts[1]};
}

static std::pair<std::optional<std::tuple<SpanString>>, std::optional<std::pair<SpanString, SpanString>>> SplitInOneOrTwo(
    const SpanString& s, std::string_view separator) {
  auto parts = Split(s, separator);
  if (parts.size() == 1) {
    return {std::make_optional(std::tuple<SpanString>(parts[0])), std::nullopt};
  }
  if (parts.size() == 2) {
    return {std::nullopt, std::make_optional(std::make_pair(parts[0], parts[1]))};
  }
  throw ParsingException(std::string("String should have been split by ") + std::string(separator) + " in 1 or 2 pieces.", s);
}

static std::vector<SpanString> SplitOnWhitespace(const SpanString& s) {
  std::vector<SpanString> ss;
  ss.push_back(s);
  const std::string seps = " \n\t";
  for (char sep : seps) {
    std::vector<SpanString> out;
    for (const auto& chunk : ss) {
      auto split = Split(chunk, std::string(1, sep));
      out.insert(out.end(), split.begin(), split.end());
    }
    ss = std::move(out);
  }
  std::vector<SpanString> nonempty;
  for (const auto& chunk : ss) {
    if (!chunk.empty()) nonempty.push_back(chunk);
  }
  return nonempty;
}

// ------------------------------
// Parsing functions.
// ------------------------------

static std::string TOO_MUCH = "too much";

static void EnactIncantations(const std::string& code) {
  if (code.find("Signa inter verba conjugo, symbolum infixus evoco!") != std::string::npos) {
    TOO_MUCH = "fun";
  }
}

static std::string FunctorSyntaxErrorMessage() {
  return "Incorrect syntax for functor call. Functor call to be made as\n"
         "  R := F(A: V, ...)\n"
         "or\n"
         "  @Make(R, F, {A: V, ...})\n"
         "Where R, F, A's and V's are all predicate names.";
}

static Json ParseExpression(const SpanString& s);
static Json ParseProposition(const SpanString& s);
static std::optional<Json> ParseCall(const SpanString& s, bool is_aggregation_allowed);
static Json ParseRecordInternals(const SpanString& s, bool is_record_literal, bool is_aggregation_allowed);

static std::optional<Json> ParseRecord(const SpanString& in) {
  SpanString s = Strip(in);
  if (s.size() >= 2 && s.at(0) == '{' && s.at(s.size() - 1) == '}' && IsWhole(s.slice(1, s.size() - 1))) {
    return ParseRecordInternals(s.slice(1, s.size() - 1), true, false);
  }
  return std::nullopt;
}

static bool IsVariableChars(const SpanString& s) {
  for (char c : s.view()) {
    if (!(std::islower(static_cast<unsigned char>(c)) || std::isdigit(static_cast<unsigned char>(c)) || c == '_')) {
      return false;
    }
  }
  return true;
}

static std::optional<Json> ParseVariable(const SpanString& s) {
  if (s.empty()) return std::nullopt;
  const char c0 = s.at(0);
  if (!(std::islower(static_cast<unsigned char>(c0)) || c0 == '_')) return std::nullopt;
  if (!IsVariableChars(s)) return std::nullopt;
  if (s.starts_with("x_")) {
    throw ParsingException("Variables starting with x_ are reserved to be Logica compiler internal. Please use a different name.", s);
  }
  return Json(JsonObject{{"var_name", Json(s.str())}});
}

static std::optional<Json> ParseNumber(SpanString s) {
  if (s.ends_with("u")) {
    s = s.slice(0, s.size() - 1);
  }
  if (s.str() == "∞") {
    return Json(JsonObject{{"number", Json("-1")}});
  }
  std::string text = s.str();
  char* end = nullptr;
  errno = 0;
  (void)std::strtod(text.c_str(), &end);
  if (errno != 0 || end == text.c_str() || *end != '\0') {
    return std::nullopt;
  }
  return Json(JsonObject{{"number", Json(text)}});
}

static std::string ParsePythonStyleStringLiteral(const SpanString& s) {
  // Supports a conservative subset of Python's string escapes:
  // \\ \n \r \t \\' \" \xhh \uhhhh.
  // This is enough for the typical Logica use cases.
  std::string_view v = s.view();
  if (v.size() < 2) return "";
  const char quote = v.front();
  std::string out;
  out.reserve(v.size());
  auto append_utf8 = [&](uint32_t code) {
    if (code <= 0x7F) {
      out.push_back(static_cast<char>(code));
    } else if (code <= 0x7FF) {
      out.push_back(static_cast<char>(0xC0 | ((code >> 6) & 0x1F)));
      out.push_back(static_cast<char>(0x80 | (code & 0x3F)));
    } else if (code <= 0xFFFF) {
      out.push_back(static_cast<char>(0xE0 | ((code >> 12) & 0x0F)));
      out.push_back(static_cast<char>(0x80 | ((code >> 6) & 0x3F)));
      out.push_back(static_cast<char>(0x80 | (code & 0x3F)));
    } else {
      out.push_back(static_cast<char>(0xF0 | ((code >> 18) & 0x07)));
      out.push_back(static_cast<char>(0x80 | ((code >> 12) & 0x3F)));
      out.push_back(static_cast<char>(0x80 | ((code >> 6) & 0x3F)));
      out.push_back(static_cast<char>(0x80 | (code & 0x3F)));
    }
  };

  for (size_t i = 1; i + 1 < v.size(); ++i) {
    char c = v[i];
    if (c != '\\') {
      out.push_back(c);
      continue;
    }
    if (i + 1 >= v.size() - 1) {
      out.push_back('\\');
      continue;
    }
    char n = v[++i];
    switch (n) {
      case '\\': out.push_back('\\'); break;
      case 'n': out.push_back('\n'); break;
      case 'r': out.push_back('\r'); break;
      case 't': out.push_back('\t'); break;
      case '\'': out.push_back('\''); break;
      case '"': out.push_back('"'); break;
      case 'x': {
        auto hex = [&](char h) -> int {
          if ('0' <= h && h <= '9') return h - '0';
          if ('a' <= h && h <= 'f') return 10 + (h - 'a');
          if ('A' <= h && h <= 'F') return 10 + (h - 'A');
          return -1;
        };
        if (i + 2 < v.size() - 1) {
          int a = hex(v[i + 1]);
          int b = hex(v[i + 2]);
          if (a >= 0 && b >= 0) {
            out.push_back(static_cast<char>(a * 16 + b));
            i += 2;
          }
        }
        break;
      }
      case 'u': {
        auto hex = [&](char h) -> int {
          if ('0' <= h && h <= '9') return h - '0';
          if ('a' <= h && h <= 'f') return 10 + (h - 'a');
          if ('A' <= h && h <= 'F') return 10 + (h - 'A');
          return -1;
        };
        if (i + 4 < v.size() - 1) {
          uint32_t code = 0;
          bool ok = true;
          for (int k = 0; k < 4; ++k) {
            int d = hex(v[i + 1 + k]);
            if (d < 0) {
              ok = false;
              break;
            }
            code = (code << 4) | d;
          }
          if (ok) {
            append_utf8(code);
            i += 4;
          }
        }
        break;
      }
      case 'U': {
        auto hex = [&](char h) -> int {
          if ('0' <= h && h <= '9') return h - '0';
          if ('a' <= h && h <= 'f') return 10 + (h - 'a');
          if ('A' <= h && h <= 'F') return 10 + (h - 'A');
          return -1;
        };
        if (i + 8 < v.size() - 1) {
          uint32_t code = 0;
          bool ok = true;
          for (int k = 0; k < 8; ++k) {
            int d = hex(v[i + 1 + k]);
            if (d < 0) {
              ok = false;
              break;
            }
            code = (code << 4) | static_cast<uint32_t>(d);
          }
          if (ok) {
            append_utf8(code);
            i += 8;
          }
        }
        break;
      }
      default:
        // Unknown escape: keep as-is (python would interpret more, but ok).
        out.push_back(n);
        break;
    }
  }
  (void)quote;
  return out;
}

static std::optional<Json> ParseString(const SpanString& s) {
  auto v = s.view();
  if (v.size() >= 2 && v.front() == '"' && v.back() == '"') {
    // Only accept if there are no quotes inside (python logic).
    if (v.substr(1, v.size() - 2).find('"') == std::string_view::npos) {
      return Json(JsonObject{{"the_string", Json(std::string(v.substr(1, v.size() - 2)))}});
    }
  }
  if (v.size() >= 2 && v.front() == '\'' && v.back() == '\'') {
    // Emulate python's screening check.
    std::string_view meat = v.substr(1, v.size() - 2);
    bool screen = false;
    bool broke = false;
    for (char c : meat) {
      if (screen) {
        screen = false;
        continue;
      }
      if (!screen && c == '\'') {
        broke = true;
        break;
      }
      if (c == '\\') {
        screen = true;
      }
    }
    // for...else: if we never break, accept.
    if (!broke) {
      // no embedded quote => literal eval is safe
      return Json(JsonObject{{"the_string", Json(ParsePythonStyleStringLiteral(s))}});
    }
  }
  if (v.size() >= 6 && v.substr(0, 3) == "\"\"\"" && v.substr(v.size() - 3) == "\"\"\"") {
    auto inner = v.substr(3, v.size() - 6);
    if (inner.find("\"\"\"") == std::string_view::npos) {
      return Json(JsonObject{{"the_string", Json(std::string(inner))}});
    }
  }
  return std::nullopt;
}

static std::optional<Json> ParseBoolean(const SpanString& s) {
  auto text = s.str();
  if (text == "true" || text == "false") {
    return Json(JsonObject{{"the_bool", Json(text)}});
  }
  return std::nullopt;
}

static std::optional<Json> ParseNull(const SpanString& s) {
  if (s.str() == "null") {
    return Json(JsonObject{{"the_null", Json("null")}});
  }
  return std::nullopt;
}

static std::optional<Json> ParseList(const SpanString& s) {
  if (s.size() >= 2 && s.at(0) == '[' && s.at(s.size() - 1) == ']' && IsWhole(s.slice(1, s.size() - 1))) {
    SpanString inside = Strip(s.slice(1, s.size() - 1));
    JsonArray elements;
    if (!inside.empty()) {
      auto elements_str = Split(inside, ",");
      for (const auto& e : elements_str) {
        elements.push_back(ParseExpression(e));
      }
    }
    return Json(JsonObject{{"element", Json(elements)}});
  }
  return std::nullopt;
}

static std::optional<Json> ParsePredicateLiteral(const SpanString& s) {
  const std::string text = s.str();
  if (text == "++?" || text == "nil") {
    return Json(JsonObject{{"predicate_name", Json(text)}});
  }
  if (text.empty()) return std::nullopt;
  if (!std::isupper(static_cast<unsigned char>(text[0]))) return std::nullopt;
  for (char c : text) {
    if (!(std::isalpha(static_cast<unsigned char>(c)) || std::isdigit(static_cast<unsigned char>(c)) || c == '_')) {
      return std::nullopt;
    }
  }
  return Json(JsonObject{{"predicate_name", Json(text)}});
}

static std::optional<Json> ParseLiteral(const SpanString& s) {
  if (auto v = ParseNumber(s)) {
    return Json(JsonObject{{"the_number", *v}});
  }
  if (auto v = ParseString(s)) {
    return Json(JsonObject{{"the_string", *v}});
  }
  if (auto v = ParseList(s)) {
    return Json(JsonObject{{"the_list", *v}});
  }
  if (auto v = ParseBoolean(s)) {
    return Json(JsonObject{{"the_bool", *v}});
  }
  if (auto v = ParseNull(s)) {
    return Json(JsonObject{{"the_null", *v}});
  }
  if (auto v = ParsePredicateLiteral(s)) {
    return Json(JsonObject{{"the_predicate", *v}});
  }
  return std::nullopt;
}

static Json ParseRecordInternals(const SpanString& in, bool is_record_literal, bool is_aggregation_allowed) {
  SpanString s = Strip(in);
  if (Split(s, ":-").size() > 1) {
    throw ParsingException("Unexpected :- in record internals.", s);
  }
  if (s.empty()) {
    return Json(JsonObject{{"field_value", Json(JsonArray{})}});
  }
  JsonArray result;
  if (IsWhole(s)) {
    auto field_values = Split(s, ",");
    bool had_restof = false;
    bool positional_ok = true;
    std::vector<std::string> observed_fields;

    for (size_t idx = 0; idx < field_values.size(); ++idx) {
      SpanString field_value = field_values[idx];
      if (had_restof) {
        throw ParsingException("Field ..<rest_of> must go last.", field_value);
      }
      if (field_value.starts_with("..")) {
        if (is_record_literal) {
          throw ParsingException("Field ..<rest_of> in record literals is not currently suppported.", field_value);
        }
        JsonObject item;
        item["field"] = Json("*");
        item["value"] = Json(JsonObject{{"expression", ParseExpression(field_value.slice_from(2))}});
        if (!observed_fields.empty()) {
          JsonArray exc;
          for (const auto& f : observed_fields) exc.push_back(Json(f));
          item["except"] = Json(exc);
        }
        result.push_back(Json(item));
        had_restof = true;
        positional_ok = false;
        continue;
      }

      std::string observed_field;
      auto [one, colon_split] = SplitInOneOrTwo(field_value, ":");
      if (colon_split) {
        positional_ok = false;
        SpanString field = colon_split->first;
        SpanString value = colon_split->second;
        observed_field = field.str();
        if (value.empty()) {
          value = field;
          if (!field.empty() && std::isupper(static_cast<unsigned char>(field.at(0)))) {
            throw ParsingException("Record fields may not start with capital letter.", field);
          }
          if (!field.empty() && field.at(0) == '`') {
            throw ParsingException("Backticks in variable names are disallowed.", field);
          }
        }
        JsonObject fv;
        fv["field"] = Json(field.str());
        fv["value"] = Json(JsonObject{{"expression", ParseExpression(value)}});
        result.push_back(Json(fv));
      } else {
        auto [qone, qsplit] = SplitInOneOrTwo(field_value, "?");
        if (qsplit) {
          if (!is_aggregation_allowed) {
            throw ParsingException("Aggregation of fields is only allowed in the head of a rule.", field_value);
          }
          positional_ok = false;
          SpanString field = qsplit->first;
          SpanString value = qsplit->second;
          observed_field = field.str();
          if (field.empty()) {
            throw ParsingException("Aggregated fields have to be named.", field_value);
          }
          auto [op, expr] = SplitInTwo(value, "=");
          op = Strip(op);
          JsonObject agg;
          agg["operator"] = Json(op.str());
          agg["argument"] = ParseExpression(expr);
          agg["expression_heritage"] = Json(value.str());

          JsonObject fv;
          fv["field"] = Json(field.str());
          fv["value"] = Json(JsonObject{{"aggregation", Json(agg)}});
          result.push_back(Json(fv));
        } else {
          if (positional_ok) {
            JsonObject fv;
            fv["field"] = Json(static_cast<int64_t>(idx));
            fv["value"] = Json(JsonObject{{"expression", ParseExpression(field_value)}});
            result.push_back(Json(fv));
            observed_field = "col" + std::to_string(idx);
          } else {
            throw ParsingException("Positional argument can not go after non-positional arguments.", field_value);
          }
        }
      }
      observed_fields.push_back(observed_field);
    }
  }
  return Json(JsonObject{{"field_value", Json(result)}});
}

// ------------------------------
// Expression parsing helpers.
// ------------------------------

static std::optional<std::pair<std::string, SpanString>> ParseGenericCall(const SpanString& in, char opening, char closing) {
  SpanString s = Strip(in);
  if (s.empty()) return std::nullopt;

  std::string predicate;
  size_t idx = 0;
  if (s.starts_with("->")) {
    idx = 2;
    predicate = "->";
  } else {
    Traverser t(s);
    TraverseStep step;
    for (;;) {
      if (!t.Next(step)) return std::nullopt;
      if (step.status != TraverseStatus::OK) {
        throw ParsingException("Parenthesis matches nothing.", s.slice(step.idx, step.idx + 1));
      }
      if (step.state == std::string(1, opening)) {
        idx = step.idx;
        std::set<char> good_chars;
        for (char c = 'a'; c <= 'z'; ++c) good_chars.insert(c);
        for (char c = 'A'; c <= 'Z'; ++c) good_chars.insert(c);
        for (char c = '0'; c <= '9'; ++c) good_chars.insert(c);
        for (char c : std::string("@_.${}+-`")) good_chars.insert(c);
        if (TOO_MUCH == "fun") {
          for (char c : std::string("*^%/")) good_chars.insert(c);
          // Some unicode operator characters.
          good_chars.insert(static_cast<char>(0));
        }
        SpanString pred_span = s.slice(0, idx);
        std::string pred = pred_span.str();
        auto all_good = [&]() {
          for (char c : pred) {
            if (good_chars.find(c) == good_chars.end()) return false;
          }
          return true;
        };
        if ((idx > 0 && all_good()) || pred == "!" || pred == "++?" || (idx >= 2 && s.at(0) == '`' && s.at(idx - 1) == '`')) {
          predicate = pred;
          break;
        }
        return std::nullopt;
      }
      if (!step.state.empty() && step.state != "{" && step.state.front() != '`') {
        return std::nullopt;
      }
    }
  }

  if (s.at(idx) == opening && s.at(s.size() - 1) == closing && IsWhole(s.slice(idx + 1, s.size() - 1))) {
    if (predicate == "`=`") predicate = "=";
    if (predicate == "`~`") predicate = "~";
    return std::make_optional(std::make_pair(predicate, s.slice(idx + 1, s.size() - 1)));
  }
  return std::nullopt;
}

static std::optional<Json> ParseInfix(const SpanString& s, std::optional<std::vector<std::string>> operators = std::nullopt,
                                      std::optional<std::set<std::string>> disallow = std::nullopt) {
  std::vector<std::string> user_defined;
  if (TOO_MUCH == "fun") {
    user_defined = {"---", "-+-", "-*-", "-/-", "-%-", "-^-"};
  }
  std::vector<std::string> ops;
  if (operators) {
    ops = *operators;
  } else {
    ops = user_defined;
    const std::vector<std::string> base = {"||", "&&", "->", "==", "<=", ">=", "<", ">", "!=", "=", "~",
                                           " in ", " is not ", " is ", "++?", "++", "+", "-", "*", "/", "%", "^", "!"};
    ops.insert(ops.end(), base.begin(), base.end());
  }
  std::set<std::string> dis = disallow ? *disallow : std::set<std::string>{};
  const std::set<std::string> unary = {"-", "!"};

  for (const auto& op : ops) {
    if (dis.find(op) != dis.end()) continue;
    auto parts = SplitRaw(s, op);
    if (parts.size() > 1) {
      SpanString left = SpanString(s.heritage, s.start, parts[parts.size() - 2].stop);
      SpanString right = SpanString(s.heritage, parts.back().start, s.stop);

      if (op == "~") {
        auto lv = left.view();
        if (!lv.empty() && lv.back() == '!') {
          continue;  // !~
        }
      }

      left = Strip(left);
      right = Strip(right);

      if (unary.find(op) != unary.end() && left.empty()) {
        JsonObject call;
        call["predicate_name"] = Json(op);
        call["record"] = ParseRecordInternals(right, false, false);
        return Json(call);
      }
      if (op == "~" && left.empty()) {
        return std::nullopt;  // negation is special.
      }

      Json left_expr = ParseExpression(left);
      Json right_expr = ParseExpression(right);
      JsonArray fvs;
      fvs.push_back(Json(JsonObject{{"field", Json("left")}, {"value", Json(JsonObject{{"expression", left_expr}})}}));
      fvs.push_back(Json(JsonObject{{"field", Json("right")}, {"value", Json(JsonObject{{"expression", right_expr}})}}));
      JsonObject rec;
      rec["field_value"] = Json(fvs);
      JsonObject call;
      std::string pred = op;
      // strip spaces around operators like " in ".
      while (!pred.empty() && std::isspace(static_cast<unsigned char>(pred.front()))) pred.erase(pred.begin());
      while (!pred.empty() && std::isspace(static_cast<unsigned char>(pred.back()))) pred.pop_back();
      call["predicate_name"] = Json(pred);
      call["record"] = Json(rec);
      return Json(call);
    }
  }
  return std::nullopt;
}

static Json BuildTreeForCombine(const Json& parsed_expression, const SpanString& op, const Json* parsed_body, const SpanString& full_text) {
  JsonObject agg;
  agg["operator"] = Json(op.str());
  agg["argument"] = parsed_expression;
  agg["expression_heritage"] = Json(full_text.str());

  JsonObject agg_fv;
  agg_fv["field"] = Json("logica_value");
  agg_fv["value"] = Json(JsonObject{{"aggregation", Json(agg)}});

  JsonObject head;
  head["predicate_name"] = Json("Combine");
  head["record"] = Json(JsonObject{{"field_value", Json(JsonArray{Json(agg_fv)})}});

  JsonObject result;
  result["head"] = Json(head);
  result["distinct_denoted"] = Json(true);
  result["full_text"] = Json(full_text.str());
  if (parsed_body) {
    result["body"] = Json(JsonObject{{"conjunction", *parsed_body}});
  }
  return Json(result);
}

static std::optional<Json> ParseCombine(const SpanString& in) {
  if (!in.starts_with("combine ")) return std::nullopt;
  SpanString s = in.slice_from(std::string("combine ").size());
  auto [one, vb] = SplitInOneOrTwo(s, ":-");
  SpanString value = s;
  std::optional<SpanString> body;
  if (vb) {
    value = vb->first;
    body = vb->second;
  }
  auto [op, expr] = SplitInTwo(value, "=");
  op = Strip(op);
  Json parsed_expression = ParseExpression(expr);
  std::optional<Json> parsed_body;
  if (body) {
    auto conj = Split(*body, ",");
    // allow singleton
    JsonArray conjuncts;
    for (const auto& c : conj) {
      conjuncts.push_back(ParseProposition(c));
    }
    parsed_body = Json(JsonObject{{"conjunct", Json(conjuncts)}});
  }
  Json tree = BuildTreeForCombine(parsed_expression, op, parsed_body ? &*parsed_body : nullptr, s);
  return Json(tree);
}

static std::optional<Json> ParseImplication(const SpanString& s) {
  if (!(s.starts_with("if ") || s.starts_with("if\n"))) return std::nullopt;
  SpanString inner = s.slice_from(3);
  auto if_thens = Split(inner, "else if");
  auto last_pair = SplitInTwo(if_thens.back(), "else");
  if_thens.back() = last_pair.first;
  SpanString last_else = last_pair.second;
  JsonArray result_if_thens;
  for (const auto& cond_cons : if_thens) {
    auto [cond, cons] = SplitInTwo(cond_cons, "then");
    result_if_thens.push_back(Json(JsonObject{{"condition", ParseExpression(cond)}, {"consequence", ParseExpression(cons)}}));
  }
  JsonObject out;
  out["if_then"] = Json(result_if_thens);
  out["otherwise"] = ParseExpression(last_else);
  return Json(out);
}

static std::optional<Json> ParseConciseCombine(const SpanString& s) {
  auto parts = Split(s, "=");
  if (parts.size() != 2) return std::nullopt;
  SpanString lhs_and_op = parts[0];
  SpanString combine = parts[1];
  auto left_parts = SplitOnWhitespace(lhs_and_op);
  if (left_parts.size() <= 1) return std::nullopt;

  SpanString lhs = SpanString(s.heritage, s.start, left_parts[left_parts.size() - 2].stop);
  SpanString op = left_parts.back();
  const std::set<std::string> prohibited = {"!", "<", ">"};
  if (prohibited.find(op.str()) != prohibited.end()) return std::nullopt;
  if (!op.empty() && std::islower(static_cast<unsigned char>(op.at(0)))) return std::nullopt;

  Json left_expr = ParseExpression(lhs);
  auto [one, expr_body] = SplitInOneOrTwo(combine, ":-");
  SpanString expr = combine;
  std::optional<SpanString> body;
  if (expr_body) {
    expr = expr_body->first;
    body = expr_body->second;
  }
  Json parsed_expression = ParseExpression(expr);
  std::optional<Json> parsed_body;
  if (body) {
    auto conj = Split(*body, ",");
    JsonArray conjuncts;
    for (const auto& c : conj) conjuncts.push_back(ParseProposition(c));
    parsed_body = Json(JsonObject{{"conjunct", Json(conjuncts)}});
  }
  Json right_expr = BuildTreeForCombine(parsed_expression, op, parsed_body ? &*parsed_body : nullptr, s);
  JsonObject rhs;
  rhs["combine"] = right_expr;
  rhs["expression_heritage"] = Json(s.str());
  JsonObject uni;
  uni["left_hand_side"] = left_expr;
  uni["right_hand_side"] = Json(rhs);
  return Json(uni);
}

static std::optional<Json> ParseUltraConciseCombine(const SpanString& s) {
  auto gc = ParseGenericCall(s, '{', '}');
  if (!gc) return std::nullopt;
  SpanString multiset = gc->second;
  SpanString op(gc->first);
  auto [one, vb] = SplitInOneOrTwo(multiset, ":-");
  SpanString value = multiset;
  std::optional<SpanString> body;
  if (vb) {
    value = vb->first;
    body = vb->second;
  }
  Json parsed_expression = ParseExpression(value);
  std::optional<Json> parsed_body;
  if (body) {
    auto conj = Split(*body, ",");
    JsonArray conjuncts;
    for (const auto& c : conj) conjuncts.push_back(ParseProposition(c));
    parsed_body = Json(JsonObject{{"conjunct", Json(conjuncts)}});
  }
  return BuildTreeForCombine(parsed_expression, op, parsed_body ? &*parsed_body : nullptr, s);
}

static std::optional<Json> ParseInclusion(const SpanString& s) {
  auto parts = Split(s, " in ");
  if (parts.size() != 2) return std::nullopt;
  JsonObject out;
  out["list"] = ParseExpression(parts[1]);
  out["element"] = ParseExpression(parts[0]);
  return Json(out);
}

static std::optional<Json> ParseCall(const SpanString& s, bool is_aggregation_allowed) {
  auto generic = ParseGenericCall(s, '(', ')');
  if (!generic) return std::nullopt;
  Json args = ParseRecordInternals(generic->second, false, is_aggregation_allowed);
  JsonObject call;
  call["predicate_name"] = Json(generic->first);
  call["record"] = args;
  return Json(call);
}

static std::optional<Json> ParseArraySub(const SpanString& s);
static Json NestedElement(const SpanString& s, const Json& array, const Json& args);

static std::optional<Json> ParseArraySub(const SpanString& s) {
  auto generic = ParseGenericCall(s, '[', ']');
  if (!generic) return std::nullopt;
  Json args = ParseRecordInternals(generic->second, false, false);
  Json array = ParseExpression(SpanString(generic->first));
  return NestedElement(s, array, args);
}

static Json NestedElement(const SpanString& s, const Json& array, const Json& args) {
  const auto& fvs = args.as_object().at("field_value").as_array();
  std::optional<Json> result;
  for (size_t i = 0; i < fvs.size(); ++i) {
    Json fv = fvs[i];
    auto& fvo = fv.as_object();
    if (!fvo.count("field")) throw ParsingException("Internal error in array subscription.", s);
    const Json& field = fvo.at("field");
    if (!field.is_int() || static_cast<size_t>(field.as_int()) != i) {
      throw ParsingException("Array subscription must only have positional arguments.", s);
    }
    fvo["field"] = Json(1);

    Json first_argument = result ? Json(JsonObject{{"call", *result}}) : array;
    JsonArray element_fvs;
    element_fvs.push_back(Json(JsonObject{{"field", Json(0)}, {"value", Json(JsonObject{{"expression", first_argument}})}}));
    element_fvs.push_back(Json(fvo));
    JsonObject element_args;
    element_args["field_value"] = Json(element_fvs);
    JsonObject call;
    call["predicate_name"] = Json("Element");
    call["record"] = Json(element_args);
    result = Json(call);
  }
  return *result;
}

static std::optional<Json> ParseUnification(const SpanString& s) {
  auto parts = Split(s, "==");
  if (parts.size() != 2) return std::nullopt;
  JsonObject out;
  out["left_hand_side"] = ParseExpression(parts[0]);
  out["right_hand_side"] = ParseExpression(parts[1]);
  return Json(out);
}

static Json NegationTree(const SpanString& s, const Json& negated_proposition) {
  Json number_one = Json(JsonObject{{"literal", Json(JsonObject{{"the_number", Json(JsonObject{{"number", Json("1")}})}})}});
  JsonObject combine;
  combine["body"] = negated_proposition;
  combine["distinct_denoted"] = Json(true);
  combine["full_text"] = Json(s.str());

  JsonObject agg;
  agg["operator"] = Json("Min");
  agg["argument"] = number_one;
  agg["expression_heritage"] = Json(s.str());
  JsonObject fv;
  fv["field"] = Json("logica_value");
  fv["value"] = Json(JsonObject{{"aggregation", Json(agg)}});
  JsonObject head;
  head["predicate_name"] = Json("Combine");
  head["record"] = Json(JsonObject{{"field_value", Json(JsonArray{Json(fv)})}});
  combine["head"] = Json(head);

  JsonObject isnull;
  isnull["predicate_name"] = Json("IsNull");
  JsonArray isnull_fvs;
  JsonObject isnull_fv;
  isnull_fv["field"] = Json(0);
  isnull_fv["value"] = Json(JsonObject{{"expression", Json(JsonObject{{"combine", Json(combine)}})}});
  isnull_fvs.push_back(Json(isnull_fv));
  isnull["record"] = Json(JsonObject{{"field_value", Json(isnull_fvs)}});
  return Json(JsonObject{{"predicate", Json(isnull)}});
}

static std::optional<Json> ParseNegation(const SpanString& s) {
  auto parts = Split(s, "~");
  if (parts.size() == 1) return std::nullopt;
  if (parts.size() != 2 || !parts[0].empty()) {
    throw ParsingException("Negation \"~\" is a unary operator.", s);
  }
  SpanString negated = Strip(parts[1]);
  auto conj_parts = Split(negated, ",");
  JsonArray conjuncts;
  for (const auto& c : conj_parts) conjuncts.push_back(ParseProposition(c));
  Json negated_prop = Json(JsonObject{{"conjunction", Json(JsonObject{{"conjunct", Json(conjuncts)}})}});
  return NegationTree(s, negated_prop);
}

static std::optional<Json> ParseNegationExpression(const SpanString& s) {
  auto proposition = ParseNegation(s);
  if (!proposition) return std::nullopt;
  JsonObject expr;
  expr["call"] = proposition->as_object().at("predicate");
  return Json(expr);
}

static std::optional<Json> ParseSubscript(const SpanString& s) {
  auto path = SplitRaw(s, ".");
  if (path.size() < 2) return std::nullopt;
  SpanString record_str = SpanString(s.heritage, s.start, path[path.size() - 2].stop);
  Json record = ParseExpression(Strip(record_str));
  SpanString last = path.back();
  for (char c : last.view()) {
    if (!(std::islower(static_cast<unsigned char>(c)) || std::isdigit(static_cast<unsigned char>(c)) || c == '_')) {
      throw ParsingException("Subscript must be lowercase.", s);
    }
  }
  Json sub = Json(JsonObject{{"literal", Json(JsonObject{{"the_symbol", Json(JsonObject{{"symbol", Json(last.str())}})}})}});
  return Json(JsonObject{{"record", record}, {"subscript", sub}});
}

static std::optional<Json> ParseDisjunction(const SpanString& s);
static std::optional<Json> ParseConjunction(const SpanString& s, bool allow_singleton);

static std::optional<Json> ParseDisjunction(const SpanString& s) {
  auto parts = Split(s, "|");
  if (parts.size() == 1) return std::nullopt;
  JsonArray disj;
  for (const auto& d : parts) disj.push_back(ParseProposition(d));
  return Json(JsonObject{{"disjunct", Json(disj)}});
}

static std::optional<Json> ParseConjunction(const SpanString& s, bool allow_singleton) {
  auto parts = Split(s, ",");
  if (parts.size() == 1 && !allow_singleton) return std::nullopt;
  JsonArray conj;
  for (const auto& c : parts) conj.push_back(ParseProposition(c));
  return Json(JsonObject{{"conjunct", Json(conj)}});
}

static Json PropositionalImplication(const SpanString& s, const SpanString& consequence_str, const Json& condition, const Json& consequence) {
  auto ensure_conjunction = [](const Json& x) -> Json {
    if (x.is_object() && x.as_object().count("conjunction")) return x;
    return Json(JsonObject{{"conjunction", Json(JsonObject{{"conjunct", Json(JsonArray{x})}})}});
  };
  JsonArray conjuncts;
  if (condition.is_object() && condition.as_object().count("conjunction")) {
    conjuncts = condition.as_object().at("conjunction").as_object().at("conjunct").as_array();
  } else {
    conjuncts = JsonArray{condition};
  }
  conjuncts.push_back(NegationTree(consequence_str, ensure_conjunction(consequence)));
  return NegationTree(s, Json(JsonObject{{"conjunction", Json(JsonObject{{"conjunct", Json(conjuncts)}})}}));
}

static std::optional<Json> ParsePropositionalImplication(const SpanString& s) {
  auto parts = Split(s, "=>");
  if (parts.size() != 2) return std::nullopt;
  Json cond = ParseProposition(parts[0]);
  Json cons = ParseProposition(parts[1]);
  return PropositionalImplication(s, parts[1], cond, cons);
}

static std::optional<Json> ParsePropositionalEquivalence(const SpanString& s) {
  auto parts = Split(s, "<=>");
  if (parts.size() != 2) return std::nullopt;
  Json left1 = ParseProposition(parts[0]);
  Json right1 = ParseProposition(parts[1]);
  Json left2 = ParseProposition(parts[0]);
  Json right2 = ParseProposition(parts[1]);
  Json a = PropositionalImplication(s, parts[1], left1, right1);
  Json b = PropositionalImplication(s, parts[0], right2, left2);
  return Json(JsonObject{{"conjunction", Json(JsonObject{{"conjunct", Json(JsonArray{a, b})}})}});
}

static Json ParseProposition(const SpanString& s) {
  if (auto c = ParseDisjunction(s)) {
    return Json(JsonObject{{"disjunction", *c}});
  }
  auto str_conjuncts = Split(s, ",");
  if (auto c = ParseConjunction(s, false); c && str_conjuncts.size() > 1) {
    return Json(JsonObject{{"conjunction", *c}});
  }
  if (TOO_MUCH == "fun") {
    if (auto c = ParsePropositionalEquivalence(s)) {
      return Json(JsonObject{{"conjunction", Json(JsonObject{{"conjunct", Json(JsonArray{*c})}})}});
    }
  }
  if (auto c = ParsePropositionalImplication(s)) {
    return *c;
  }
  if (auto c = ParseImplication(s)) {
    throw ParsingException("If-then-else clause is only supported as an expression, not as a proposition.", s);
  }
  if (auto c = ParseCall(s, false)) {
    return Json(JsonObject{{"predicate", *c}});
  }
  if (auto c = ParseInfix(s, std::make_optional(std::vector<std::string>{"&&", "||"}), std::nullopt)) {
    return Json(JsonObject{{"predicate", *c}});
  }
  if (auto u = ParseUnification(s)) {
    return Json(JsonObject{{"unification", *u}});
  }
  if (auto inc = ParseInclusion(s)) {
    return Json(JsonObject{{"inclusion", *inc}});
  }
  if (auto cc = ParseConciseCombine(s)) {
    return Json(JsonObject{{"unification", *cc}});
  }
  if (auto inf = ParseInfix(s)) {
    return Json(JsonObject{{"predicate", *inf}});
  }
  if (auto neg = ParseNegation(s)) {
    return *neg;
  }
  throw ParsingException("Could not parse proposition.", s);
}

static Json ActuallyParseExpression(const SpanString& s) {
  if (auto v = ParseCombine(s)) {
    return Json(JsonObject{{"combine", *v}});
  }
  if (auto v = ParseImplication(s)) {
    return Json(JsonObject{{"implication", *v}});
  }
  if (auto v = ParseLiteral(s)) {
    return Json(JsonObject{{"literal", *v}});
  }
  if (auto v = ParseVariable(s)) {
    return Json(JsonObject{{"variable", *v}});
  }
  if (auto v = ParseRecord(s)) {
    return Json(JsonObject{{"record", *v}});
  }
  if (auto v = ParsePropositionalImplication(s)) {
    // In python: return {'call': v['predicate']}
    if (v->is_object() && v->as_object().count("predicate")) {
      return Json(JsonObject{{"call", v->as_object().at("predicate")}});
    }
  }
  if (auto v = ParseCall(s, false)) {
    return Json(JsonObject{{"call", *v}});
  }
  if (auto v = ParseUltraConciseCombine(s)) {
    return Json(JsonObject{{"combine", *v}});
  }
  if (auto v = ParseInfix(s, std::nullopt, std::make_optional(std::set<std::string>{"~"}))) {
    return Json(JsonObject{{"call", *v}});
  }
  if (auto v = ParseSubscript(s)) {
    return Json(JsonObject{{"subscript", *v}});
  }
  if (auto v = ParseNegationExpression(s)) {
    return *v;
  }
  if (auto v = ParseArraySub(s)) {
    return Json(JsonObject{{"call", *v}});
  }
  throw ParsingException("Could not parse expression of a value.", s);
}

static Json ParseExpression(const SpanString& s) {
  Json e = ActuallyParseExpression(s);
  e.as_object()["expression_heritage"] = Json(s.str());
  return e;
}

// ------------------------------
// Rule parsing.
// ------------------------------

static std::pair<Json, bool> ParseHeadCall(const SpanString& s, bool distinct_from_outside) {
  bool saw_open = false;
  size_t idx = 0;
  Traverser t(s);
  TraverseStep step;
  while (t.Next(step)) {
    if (step.status != TraverseStatus::OK) {
      throw ParsingException("Parenthesis matches nothing.", s.slice(step.idx, step.idx + 1));
    }
    if (step.state == "(") {
      saw_open = true;
    }
    if (saw_open && step.state.empty()) {
      idx = step.idx;
      break;
    }
  }
  if (!saw_open) throw ParsingException("Found no call in rule head.", s);

  SpanString call_str = s.slice(0, idx + 1);
  SpanString post_call_str = s.slice_from(idx + 1);
  auto call = ParseCall(call_str, true);
  if (!call) throw ParsingException("Could not parse predicate call.", call_str);

  auto check_agg = [&](const Json& callj) {
    if (distinct_from_outside) return;
    const auto& fvs = callj.as_object().at("record").as_object().at("field_value").as_array();
    for (const auto& fv : fvs) {
      const auto& fvo = fv.as_object();
      if (fvo.at("value").as_object().count("aggregation")) {
        throw ParsingException("Aggregation appears in a non-distinct predicate. Did you forget distinct?", call_str);
      }
    }
  };

  auto op_expr = Split(post_call_str, "=");
  if (op_expr.size() == 1) {
    if (!op_expr[0].empty()) {
      throw ParsingException("Unexpected text in the head of a rule.", op_expr[0]);
    }
    check_agg(*call);
    return {*call, false};
  }
  if (op_expr.size() > 2) {
    throw ParsingException("Too many '=' in predicate value.", post_call_str);
  }

  SpanString op_str = op_expr[0];
  SpanString expr_str = op_expr[1];
  if (op_str.empty()) {
    auto& fvs = call->as_object().at("record").as_object().at("field_value").as_array();
    fvs.push_back(Json(JsonObject{{"field", Json("logica_value")}, {"value", Json(JsonObject{{"expression", ParseExpression(expr_str)}})}}));
    check_agg(*call);
    return {*call, false};
  }

  JsonObject agg;
  agg["operator"] = Json(op_str.str());
  agg["argument"] = ParseExpression(expr_str);
  agg["expression_heritage"] = Json(post_call_str.str());
  JsonObject fv;
  fv["field"] = Json("logica_value");
  fv["value"] = Json(JsonObject{{"aggregation", Json(agg)}});
  call->as_object().at("record").as_object().at("field_value").as_array().push_back(Json(fv));
  return {*call, true};
}

static std::optional<Json> ParseFunctorRule(const SpanString& s) {
  auto parts = Split(s, ":=");
  if (parts.size() != 2) return std::nullopt;
  Json new_predicate = ParseExpression(parts[0]);
  Json definition_expr = ParseExpression(parts[1]);
  if (!definition_expr.as_object().count("call")) {
    throw ParsingException(FunctorSyntaxErrorMessage(), parts[1]);
  }
  Json definition = definition_expr.as_object().at("call");
  if (!(new_predicate.as_object().count("literal") &&
        new_predicate.as_object().at("literal").as_object().count("the_predicate"))) {
    throw ParsingException(FunctorSyntaxErrorMessage(), parts[0]);
  }

  Json applicant = Json(JsonObject{{"expression", Json(JsonObject{{"literal", Json(JsonObject{{"the_predicate", Json(JsonObject{{"predicate_name", definition.as_object().at("predicate_name")}})}})}})}});
  Json arguments = Json(JsonObject{{"expression", Json(JsonObject{{"record", definition.as_object().at("record")}})}});
  JsonObject rule;
  rule["full_text"] = Json(s.str());
  JsonObject head;
  head["predicate_name"] = Json("@Make");
  JsonArray fvs;
  fvs.push_back(Json(JsonObject{{"field", Json(0)}, {"value", Json(JsonObject{{"expression", new_predicate}})}}));
  fvs.push_back(Json(JsonObject{{"field", Json(1)}, {"value", applicant}}));
  fvs.push_back(Json(JsonObject{{"field", Json(2)}, {"value", arguments}}));
  head["record"] = Json(JsonObject{{"field_value", Json(fvs)}});
  rule["head"] = Json(head);
  return Json(rule);
}

static std::tuple<SpanString, bool, std::optional<Json>> GrabDenotation(const SpanString& head, std::string_view denotation, bool with_arguments) {
  auto head_couldbe = Split(head, denotation);
  if (head_couldbe.size() > 2) {
    throw ParsingException("Too many denotations.", head);
  }
  if (with_arguments) {
    if (head_couldbe.size() == 2) {
      SpanString arg = Strip(head_couldbe[1]);
      if (!arg.empty() && arg.at(0) == '(') {
        throw ParsingException("Can not parse denotations when extracting.", head);
      }
      Json args = ParseRecordInternals(arg, false, false);
      return {head_couldbe[0], true, args};
    }
    return {head, false, std::nullopt};
  }
  if (head_couldbe.size() == 2) {
    if (!StripSpaces(head_couldbe[1]).empty()) {
      throw ParsingException("Too many denotations or incorrect place.", head);
    }
    return {head_couldbe[0], true, std::nullopt};
  }
  return {head, false, std::nullopt};
}

static Json ParseRule(const SpanString& s);

static std::optional<std::pair<Json, Json>> ParseFunctionRuleImpl(const SpanString& s) {
  auto parts = SplitRaw(s, "-->");
  if (parts.size() != 2) return std::nullopt;
  auto this_call = ParseCall(parts[0], false);
  if (!this_call) {
    throw ParsingException("Left hand side of function definition must be a predicate call.", parts[0]);
  }
  std::string pred_name = this_call->as_object().at("predicate_name").as_string();
  Json annotation_rule = ParseRule(SpanString("@CompileAsUdf(" + pred_name + ")"));
  Json rule = ParseRule(SpanString(parts[0].str() + " = " + parts[1].str()));
  return std::make_optional(std::make_pair(annotation_rule, rule));
}

static Json ParseRule(const SpanString& s) {
  auto parts = Split(s, ":-");
  if (parts.size() > 2) {
    throw ParsingException("Too many :- in a rule. Did you forget semicolon?", s);
  }
  SpanString head = parts[0];
  auto [h1, couldbe, none1] = GrabDenotation(head, "couldbe", false);
  auto [h2, cantbe, none2] = GrabDenotation(h1, "cantbe", false);
  auto [h3, shouldbe, none3] = GrabDenotation(h2, "shouldbe", false);
  auto [h4, limit, limit_what] = GrabDenotation(h3, "limit", true);
  auto [h5, order_by, order_by_what] = GrabDenotation(h4, "order_by", true);
  head = h5;

  auto head_distinct = Split(head, "distinct");
  JsonObject result;
  if (head_distinct.size() == 1) {
    auto [parsed_head, is_distinct] = ParseHeadCall(head, false);
    result["head"] = parsed_head;
    if (is_distinct) result["distinct_denoted"] = Json(true);
  } else {
    if (!(head_distinct.size() == 2 && head_distinct[1].empty())) {
      throw ParsingException("Can not parse rule head. Something is wrong with distinct.", head);
    }
    auto [parsed_head, is_distinct] = ParseHeadCall(head_distinct[0], true);
    (void)is_distinct;
    result["head"] = parsed_head;
    result["distinct_denoted"] = Json(true);
  }
  if (couldbe) result["couldbe_denoted"] = Json(true);
  if (cantbe) result["cantbe_denoted"] = Json(true);
  if (shouldbe) result["shouldbe_denoted"] = Json(true);
  if (order_by) result["orderby_denoted"] = *order_by_what;
  if (limit) result["limit_denoted"] = *limit_what;
  if (parts.size() == 2) {
    result["body"] = ParseProposition(parts[1]);
  }
  result["full_text"] = Json(s.str());
  return Json(result);
}

// ------------------------------
// Imports, renaming, and rewrites.
// ------------------------------

static std::tuple<std::string, std::string, std::optional<std::string>> SplitImport(const std::string& import_str) {
  size_t pos = import_str.find(" as ");
  std::string import_path = import_str;
  std::optional<std::string> synonym;
  if (pos != std::string::npos) {
    if (import_str.find(" as ", pos + 1) != std::string::npos) {
      throw ParsingException("Too many as", SpanString(import_str));
    }
    import_path = import_str.substr(0, pos);
    synonym = import_str.substr(pos + 4);
  }
  std::vector<std::string> parts;
  std::string tmp;
  std::istringstream iss(import_path);
  while (std::getline(iss, tmp, '.')) parts.push_back(tmp);
  if (parts.empty() || parts.back().empty() || !std::isupper(static_cast<unsigned char>(parts.back()[0]))) {
    throw ParsingException("One import per predicate please.", SpanString(import_str));
  }
  std::string predicate = parts.back();
  parts.pop_back();
  std::string file;
  for (size_t i = 0; i < parts.size(); ++i) {
    if (i) file += '.';
    file += parts[i];
  }
  return {file, predicate, synonym};
}

static bool HasKey(const Json& j, const std::string& k) {
  return j.is_object() && j.as_object().count(k);
}

static int RenamePredicate(Json& e, const std::string& old_name, const std::string& new_name) {
  int count = 0;
  if (e.is_object()) {
    auto& o = e.as_object();
    auto it = o.find("predicate_name");
    if (it != o.end() && it->second.is_string() && it->second.as_string() == old_name) {
      it->second = Json(new_name);
      count++;
    }
    auto itf = o.find("field");
    if (itf != o.end() && itf->second.is_string() && itf->second.as_string() == old_name) {
      itf->second = Json(new_name);
      count++;
    }
    for (auto& [k, v] : o) {
      if (v.is_object() || v.is_array()) count += RenamePredicate(v, old_name, new_name);
    }
  } else if (e.is_array()) {
    for (auto& v : e.as_array()) {
      if (v.is_object() || v.is_array()) count += RenamePredicate(v, old_name, new_name);
    }
  }
  return count;
}

static std::set<std::string> DefinedPredicates(const JsonArray& rules) {
  std::set<std::string> out;
  for (const auto& r : rules) {
    const auto& head = r.as_object().at("head").as_object();
    out.insert(head.at("predicate_name").as_string());
  }
  return out;
}

static std::set<std::string> MadePredicates(const JsonArray& rules) {
  std::set<std::string> out;
  for (const auto& r : rules) {
    const auto& ro = r.as_object();
    if (ro.at("head").as_object().at("predicate_name").as_string() == "@Make") {
      const auto& fv0 = ro.at("head").as_object().at("record").as_object().at("field_value").as_array().at(0);
      const auto& name = fv0.as_object().at("value").as_object().at("expression").as_object().at("literal").as_object().at("the_predicate").as_object().at("predicate_name").as_string();
      out.insert(name);
    }
  }
  return out;
}

static Json StripAggregationHeritage(const Json& field_values) {
  Json copy = field_values;
  for (auto& fv : copy.as_array()) {
    auto& vobj = fv.as_object().at("value").as_object();
    if (vobj.count("aggregation")) {
      vobj.at("aggregation").as_object().erase("expression_heritage");
    }
  }
  return copy;
}

static Json MultiBodyAggregationRewrite(const Json& rules_json) {
  Json rules_copy = rules_json;
  JsonArray rules = rules_copy.as_array();
  // Preserve insertion order of predicate names (python dict preserves insertion order).
  std::unordered_map<std::string, std::vector<Json>> by_name;
  std::vector<std::string> names_in_order;
  names_in_order.reserve(rules.size());
  for (const auto& r : rules) {
    std::string name = r.as_object().at("head").as_object().at("predicate_name").as_string();
    auto it = by_name.find(name);
    if (it == by_name.end()) {
      names_in_order.push_back(name);
      by_name.emplace(name, std::vector<Json>{r});
    } else {
      it->second.push_back(r);
    }
  }
  std::vector<std::string> multi;
  for (const auto& n : names_in_order) {
    const auto& rs = by_name.at(n);
    if (rs.size() > 1 && rs[0].as_object().count("distinct_denoted")) {
      multi.push_back(n);
    }
  }

  JsonArray new_rules;
  std::map<std::string, Json> agg_fvs_per_pred;
  std::map<std::string, std::string> original_full_text;

  auto split_aggregation = [&](const Json& rule) -> std::pair<Json, Json> {
    Json r = rule;
    if (!r.as_object().count("distinct_denoted")) {
      throw ParsingException("Inconsistency in distinct denoting.", SpanString(rule.as_object().at("head").as_object().at("predicate_name").as_string()));
    }
    r.as_object().erase("distinct_denoted");
    std::string name = r.as_object().at("head").as_object().at("predicate_name").as_string();
    r.as_object().at("head").as_object().at("predicate_name") = Json(name + "_MultBodyAggAux");

    JsonArray transformation;
    JsonArray aggregation;
    const auto& fvs = r.as_object().at("head").as_object().at("record").as_object().at("field_value").as_array();
    for (const auto& fv : fvs) {
      const auto& fvo = fv.as_object();
      const Json& field = fvo.at("field");
      const auto& value = fvo.at("value").as_object();
      if (value.count("aggregation")) {
        const auto& a = value.at("aggregation").as_object();
        JsonObject agg_a;
        agg_a["operator"] = a.at("operator");
        agg_a["argument"] = Json(JsonObject{{"variable", Json(JsonObject{{"var_name", field}})}});
        agg_a["expression_heritage"] = a.at("expression_heritage");
        aggregation.push_back(Json(JsonObject{{"field", field}, {"value", Json(JsonObject{{"aggregation", Json(agg_a)}})}}));
        transformation.push_back(Json(JsonObject{{"field", field}, {"value", Json(JsonObject{{"expression", a.at("argument")}})}}));
      } else {
        aggregation.push_back(Json(JsonObject{{"field", field}, {"value", Json(JsonObject{{"expression", Json(JsonObject{{"variable", Json(JsonObject{{"var_name", field}})}})}})}}));
        transformation.push_back(fv);
      }
    }
    r.as_object().at("head").as_object().at("record").as_object().at("field_value") = Json(transformation);
    return {Json(aggregation), r};
  };

  for (const auto& rule : rules) {
    std::string name = rule.as_object().at("head").as_object().at("predicate_name").as_string();
    original_full_text[name] = rule.as_object().at("full_text").as_string();
    if (std::find(multi.begin(), multi.end(), name) != multi.end()) {
      auto [aggregation_fvs, new_rule] = split_aggregation(rule);
      if (agg_fvs_per_pred.count(name)) {
        Json expected = StripAggregationHeritage(agg_fvs_per_pred[name].as_object().at("field_value"));
        Json observed = StripAggregationHeritage(aggregation_fvs);
        if (expected.ToString(false) != observed.ToString(false)) {
          throw ParsingException("Signature differs for bodies.", SpanString(rule.as_object().at("full_text").as_string()));
        }
      } else {
        agg_fvs_per_pred[name] = Json(JsonObject{{"field_value", aggregation_fvs}});
      }
      new_rules.push_back(new_rule);
    } else {
      new_rules.push_back(rule);
    }
  }

  for (const auto& name : multi) {
    const auto& agg_fvs = agg_fvs_per_pred.at(name).as_object().at("field_value").as_array();
    JsonArray pass_fvs;
    for (const auto& fv : agg_fvs) {
      const Json& field = fv.as_object().at("field");
      pass_fvs.push_back(Json(JsonObject{{"field", field}, {"value", Json(JsonObject{{"expression", Json(JsonObject{{"variable", Json(JsonObject{{"var_name", field}})}})}})}}));
    }
    JsonObject aggregating_rule;
    {
      JsonObject head;
      head["predicate_name"] = Json(name);
      head["record"] = Json(JsonObject{{"field_value", Json(agg_fvs)}});
      aggregating_rule["head"] = Json(head);
    }
    {
      JsonObject aux_pred;
      aux_pred["predicate_name"] = Json(name + "_MultBodyAggAux");
      aux_pred["record"] = Json(JsonObject{{"field_value", Json(pass_fvs)}});

      JsonObject proposition;
      proposition["predicate"] = Json(aux_pred);

      JsonObject conjunction;
      conjunction["conjunct"] = Json(JsonArray{Json(proposition)});

      JsonObject body;
      body["conjunction"] = Json(conjunction);
      aggregating_rule["body"] = Json(body);
    }
    aggregating_rule["full_text"] = Json(original_full_text[name]);
    aggregating_rule["distinct_denoted"] = Json(true);
    new_rules.push_back(Json(aggregating_rule));
  }

  return Json(new_rules);
}

static Json DnfRewrite(const Json& rules_json) {
  using Dnf = std::vector<std::vector<Json>>;

  std::function<Dnf(const Json&)> proposition_to_dnf;
  std::function<std::vector<std::vector<Json>>(const std::vector<Dnf>&)> conjunction_of_dnfs;

  conjunction_of_dnfs = [&](const std::vector<Dnf>& dnfs) -> Dnf {
    if (dnfs.empty()) return Dnf{{}};
    if (dnfs.size() == 1) return dnfs[0];
    Dnf result;
    const Dnf& first = dnfs[0];
    std::vector<Dnf> rest(dnfs.begin() + 1, dnfs.end());
    Dnf other = conjunction_of_dnfs(rest);
    for (const auto& a : first) {
      for (const auto& b : other) {
        std::vector<Json> merged = a;
        merged.insert(merged.end(), b.begin(), b.end());
        result.push_back(std::move(merged));
      }
    }
    return result;
  };

  proposition_to_dnf = [&](const Json& prop) -> Dnf {
    if (HasKey(prop, "conjunction")) {
      std::vector<Dnf> dnfs;
      for (const auto& c : prop.as_object().at("conjunction").as_object().at("conjunct").as_array()) {
        dnfs.push_back(proposition_to_dnf(c));
      }
      return conjunction_of_dnfs(dnfs);
    }
    if (HasKey(prop, "disjunction")) {
      Dnf result;
      for (const auto& d : prop.as_object().at("disjunction").as_object().at("disjunct").as_array()) {
        Dnf dd = proposition_to_dnf(d);
        result.insert(result.end(), dd.begin(), dd.end());
      }
      return result;
    }
    return Dnf{{prop}};
  };

  JsonArray out;
  for (const auto& rule : rules_json.as_array()) {
    if (!HasKey(rule, "body")) {
      out.push_back(rule);
      continue;
    }
    auto dnf = proposition_to_dnf(rule.as_object().at("body"));
    for (const auto& conjuncts : dnf) {
      Json new_rule = rule;
      JsonArray conj = conjuncts;
      new_rule.as_object()["body"] = Json(JsonObject{{"conjunction", Json(JsonObject{{"conjunct", Json(conj)}})}});
      out.push_back(new_rule);
    }
  }
  return Json(out);
}

static std::string AggregationOperator(const std::string& raw) {
  if (raw == "+") return "Agg+";
  if (raw == "++") return "Agg++";
  if (raw == "*") return "`*`";
  return raw;
}

static Json AggregationConvert(const Json& a) {
  JsonObject call;
  call["predicate_name"] = Json(AggregationOperator(a.as_object().at("operator").as_string()));
  JsonArray fvs;
  fvs.push_back(Json(JsonObject{{"field", Json(0)}, {"value", Json(JsonObject{{"expression", a.as_object().at("argument")}})}}));
  call["record"] = Json(JsonObject{{"field_value", Json(fvs)}});
  JsonObject out;
  out["call"] = Json(call);
  out["expression_heritage"] = a.as_object().at("expression_heritage");
  return Json(out);
}

static void RewriteAggregationsInternal(Json& node) {
  if (node.is_object()) {
    auto& o = node.as_object();
    for (auto& [k, v] : o) {
      if (v.is_object()) {
        auto& vo = v.as_object();
        auto it = vo.find("aggregation");
        if (it != vo.end() && it->second.is_object()) {
          Json a = it->second;
          Json expr = AggregationConvert(a);
          it->second.as_object().erase("operator");
          it->second.as_object().erase("argument");
          it->second.as_object()["expression"] = expr;
        }
      }
    }
    for (auto& [k, v] : o) {
      if (v.is_object() || v.is_array()) RewriteAggregationsInternal(v);
    }
  } else if (node.is_array()) {
    for (auto& v : node.as_array()) {
      if (v.is_object() || v.is_array()) RewriteAggregationsInternal(v);
    }
  }
}

static Json RewriteAggregationsAsExpressions(const Json& rules) {
  Json copy = rules;
  RewriteAggregationsInternal(copy);
  return copy;
}

static JsonArray AnnotationsFromDenotations(Json& rule) {
  JsonArray result;
  auto shift_args = [](Json& fvs) {
    for (auto& fv : fvs.as_array()) {
      auto& field = fv.as_object().at("field");
      if (field.is_int()) field = Json(field.as_int() + 1);
    }
  };
  for (const auto& [denotation, annotation] : std::vector<std::pair<std::string, std::string>>{{"orderby_denoted", "@OrderBy"}, {"limit_denoted", "@Limit"}}) {
    auto& ro = rule.as_object();
    if (!ro.count(denotation)) continue;
    // Python mutates the rule's denotation args in-place (ShiftArgs).
    shift_args(ro.at(denotation).as_object().at("field_value"));
    Json args = ro.at(denotation);
    JsonObject ann;
    ann["full_text"] = ro.at("full_text");
    JsonObject head;
    head["predicate_name"] = Json(annotation);
    JsonArray fvs;
    fvs.push_back(Json(JsonObject{{"field", Json(0)}, {"value", Json(JsonObject{{"expression", Json(JsonObject{{"literal", Json(JsonObject{{"the_predicate", Json(JsonObject{{"predicate_name", ro.at("head").as_object().at("predicate_name")}})}})}})}})}}));
    for (const auto& fv : args.as_object().at("field_value").as_array()) fvs.push_back(fv);
    head["record"] = Json(JsonObject{{"field_value", Json(fvs)}});
    ann["head"] = Json(head);
    result.push_back(Json(ann));
  }
  return result;
}

static Json ParseFileInternal(const std::string& content,
                              const std::string& this_file_name,
                              std::map<std::string, Json>& parsed_imports,
                              std::set<std::string>& in_progress,
                              std::vector<std::string> import_chain,
                              const std::vector<std::string>& import_root);

static Json ParseImport(const std::string& file_import_str,
                        std::map<std::string, Json>& parsed_imports,
                        std::set<std::string>& in_progress,
                        const std::vector<std::string>& import_chain,
                        const std::vector<std::string>& import_root) {
  if (parsed_imports.count(file_import_str)) {
    return parsed_imports.at(file_import_str);
  }
  if (in_progress.count(file_import_str)) {
    std::string chain;
    for (const auto& c : import_chain) chain += c + "->";
    chain += file_import_str;
    throw ParsingException("Circular imports are not allowed: " + chain, SpanString(file_import_str));
  }
  in_progress.insert(file_import_str);

  std::vector<std::string> parts;
  std::string tmp;
  std::istringstream iss(file_import_str);
  while (std::getline(iss, tmp, '.')) parts.push_back(tmp);
  std::string rel;
  for (size_t i = 0; i < parts.size(); ++i) {
    if (i) rel += '/';
    rel += parts[i];
  }
  rel += ".l";

  std::filesystem::path found;
  bool ok = false;
  std::vector<std::string> roots = import_root;
  if (roots.empty()) roots.push_back("");
  for (const auto& root : roots) {
    std::filesystem::path p = std::filesystem::path(root) / rel;
    if (std::filesystem::exists(p)) {
      found = p;
      ok = true;
      break;
    }
  }
  if (!ok) {
    throw ParsingException("Imported file not found: " + rel, SpanString("import " + file_import_str + ".<PREDICATE>").slice(7, 7 + file_import_str.size()));
  }

  std::ifstream f(found);
  std::ostringstream oss;
  oss << f.rdbuf();
  std::string file_content = oss.str();
  Json parsed = ParseFileInternal(file_content, file_import_str, parsed_imports, in_progress, import_chain, import_root);
  parsed_imports[file_import_str] = parsed;
  in_progress.erase(file_import_str);
  return parsed;
}

static Json ParseFileInternal(const std::string& content,
                              const std::string& this_file_name,
                              std::map<std::string, Json>& parsed_imports,
                              std::set<std::string>& in_progress,
                              std::vector<std::string> import_chain,
                              const std::vector<std::string>& import_root) {
  if ((this_file_name.empty() ? std::string("main") : this_file_name) == "main") {
    EnactIncantations(content);
  }

  // Update chain for circular import errors.
  import_chain.push_back(this_file_name);

  SpanString s{std::string(RemoveComments(SpanString(content)))};
  auto statements = Split(s, ";");
  JsonArray rules;
  JsonArray imported_predicates;
  std::map<std::string, std::set<std::string>> predicates_created_by_import;

  for (const auto& st : statements) {
    if (st.empty()) continue;
    if (st.starts_with("import ")) {
      std::string import_str = st.slice_from(std::string("import ").size()).str();
      auto [file_import_str, import_predicate, synonym] = SplitImport(import_str);
      Json parsed = ParseImport(file_import_str, parsed_imports, in_progress, import_chain, import_root);
      JsonObject ip;
      ip["file"] = Json(file_import_str);
      ip["predicate_name"] = Json(import_predicate);
      ip["synonym"] = synonym ? Json(*synonym) : Json(nullptr);
      imported_predicates.push_back(Json(ip));
      if (!predicates_created_by_import.count(file_import_str)) {
        const auto& prules = parsed.as_object().at("rule").as_array();
        auto def = DefinedPredicates(prules);
        auto made = MadePredicates(prules);
        def.insert(made.begin(), made.end());
        predicates_created_by_import[file_import_str] = std::move(def);
      }
      continue;
    }

    std::optional<Json> rule;
    if (auto ann = ParseFunctionRuleImpl(st)) {
      rules.push_back(ann->first);
      rule = ann->second;
    }
    if (!rule) {
      rule = ParseFunctorRule(st);
    }
    if (!rule) {
      Json r = ParseRule(st);
      if (!r.is_null()) {
        auto anns = AnnotationsFromDenotations(r);
        for (const auto& a : anns) rules.push_back(a);
        rule = r;
      }
    }
    if (rule) rules.push_back(*rule);
  }

  // Rewrites.
  Json rewritten = DnfRewrite(Json(rules));
  rewritten = MultiBodyAggregationRewrite(rewritten);
  rewritten = RewriteAggregationsAsExpressions(rewritten);
  rules = rewritten.as_array();

  // Prefix.
  std::string prefix;
  if (this_file_name == "main") {
    prefix = "";
  } else {
    std::set<std::string> existing;
    for (const auto& [k, v] : parsed_imports) {
      if (v.is_object() && v.as_object().count("predicates_prefix")) {
        existing.insert(v.as_object().at("predicates_prefix").as_string());
      }
    }
    std::vector<std::string> parts;
    std::string tmp;
    std::istringstream iss(this_file_name);
    while (std::getline(iss, tmp, '.')) parts.push_back(tmp);
    int idx = static_cast<int>(parts.size()) - 1;
    auto capitalize = [](std::string x) {
      if (x.empty()) return x;
      x[0] = static_cast<char>(std::toupper(static_cast<unsigned char>(x[0])));
      for (size_t i = 1; i < x.size(); ++i) x[i] = static_cast<char>(std::tolower(static_cast<unsigned char>(x[i])));
      return x;
    };
    prefix = capitalize(parts[idx]) + "_";
    while (existing.count(prefix)) {
      idx -= 1;
      if (idx <= 0) {
        throw ParsingException("Import paths equal modulo _ and /.", SpanString(prefix));
      }
      prefix = parts[idx] + prefix;
    }
  }

  // Rename predicates for non-main.
  if (this_file_name != "main") {
    auto def = DefinedPredicates(rules);
    auto made = MadePredicates(rules);
    def.insert(made.begin(), made.end());
    for (const auto& p : def) {
      if (!p.empty() && p[0] != '@' && p != "++?") {
        Json rr(rules);
        for (auto& r : rr.as_array()) {
          RenamePredicate(r, p, prefix + p);
        }
        rules = rr.as_array();
      }
    }
  }

  // Apply imported predicate renames and checks.
  for (const auto& ipj : imported_predicates) {
    const auto& ip = ipj.as_object();
    std::string file = ip.at("file").as_string();
    std::string imported_pred_name = ip.at("predicate_name").as_string();
    std::string imported_as = ip.at("synonym").is_null() ? imported_pred_name : ip.at("synonym").as_string();
    std::string import_prefix = parsed_imports.at(file).as_object().at("predicates_prefix").as_string();
    if (import_prefix.empty()) {
      throw ParsingException("Empty import prefix", SpanString(file));
    }
    int rename_count = 0;
    for (auto& r : rules) {
      rename_count += RenamePredicate(r, imported_as, import_prefix + imported_pred_name);
    }
    if (!predicates_created_by_import[file].count(import_prefix + imported_pred_name) &&
        !predicates_created_by_import[file].count(imported_pred_name)) {
      throw ParsingException("Predicate imported but not defined.", SpanString(file + " -> " + imported_pred_name));
    }
    if (rename_count == 0) {
      throw ParsingException("Predicate imported but not used.", SpanString(file + " -> " + imported_as));
    }
  }

  // Main assembles all rules.
  if (this_file_name == "main") {
    auto defined = DefinedPredicates(rules);
    for (const auto& [k, v] : parsed_imports) {
      const auto& irules = v.as_object().at("rule").as_array();
      auto new_preds = DefinedPredicates(irules);
      for (const auto& p : new_preds) {
        if (defined.count(p) && !p.empty() && p[0] != '@') {
          throw ParsingException("Predicate from file is overridden by importer.", SpanString(p));
        }
      }
      defined.insert(new_preds.begin(), new_preds.end());
      rules.insert(rules.end(), irules.begin(), irules.end());
    }
  }

  JsonObject out;
  out["rule"] = Json(rules);
  out["imported_predicates"] = Json(imported_predicates);
  out["predicates_prefix"] = Json(prefix);
  out["file_name"] = Json(this_file_name);
  return Json(out);
}

static Json ParseFile(const std::string& content,
                      const std::string& file_name = "main",
                      const std::vector<std::string>& import_root = {}) {
  std::map<std::string, Json> parsed_imports;
  std::set<std::string> in_progress;
  return ParseFileInternal(content, file_name, parsed_imports, in_progress, {}, import_root);
}

}  // namespace logica::parser

// ------------------------------
// C ABI (for Python ctypes / native integration).
// ------------------------------

static std::vector<std::string> SplitLogicapath(const char* lp) {
  std::vector<std::string> roots;
  if (!lp) return roots;
  std::string s(lp);
  size_t start = 0;
  while (start <= s.size()) {
    size_t pos = s.find(':', start);
    if (pos == std::string::npos) pos = s.size();
    std::string part = s.substr(start, pos - start);
    if (!part.empty()) roots.push_back(part);
    start = pos + 1;
  }
  return roots;
}

static char* DupToMalloc(std::string_view s) {
  char* p = static_cast<char*>(std::malloc(s.size() + 1));
  if (!p) return nullptr;
  std::memcpy(p, s.data(), s.size());
  p[s.size()] = '\0';
  return p;
}

extern "C" {

// Returns 0 on success and sets *out_json.
// Returns non-zero on error and sets *out_err.
// Caller must free returned buffers via logica_cpp_free().
int logica_cpp_parse_rules_json(const char* program_text,
                                const char* file_name,
                                const char* logicapath,
                                int full,
                                void** out_json,
                                void** out_err) {
  if (out_json) *out_json = nullptr;
  if (out_err) *out_err = nullptr;
  try {
    const std::string content = program_text ? std::string(program_text) : std::string();
    const std::string fname = file_name ? std::string(file_name) : std::string("main");
    std::vector<std::string> import_root = SplitLogicapath(logicapath);

    logica::parser::Json parsed = logica::parser::ParseFile(content, fname, import_root);
    std::string out;
    if (full) {
      out = parsed.ToString(true, 1);
    } else {
      const auto& obj = parsed.as_object();
      auto it = obj.find("rule");
      out = (it == obj.end()) ? std::string("[]") : it->second.ToString(true, 1);
    }
    if (out_json) {
      *out_json = DupToMalloc(out);
    }
    return 0;
  } catch (const logica::parser::ParsingException& e) {
    std::ostringstream oss;
    e.ShowMessage(oss);
    if (out_err) {
      *out_err = DupToMalloc(oss.str());
    }
    return 1;
  } catch (const std::exception& e) {
    std::string msg = std::string("Error: ") + e.what() + "\n";
    if (out_err) {
      *out_err = DupToMalloc(msg);
    }
    return 2;
  }
}

void logica_cpp_free(void* p) {
  std::free(p);
}

}  // extern "C"

// ------------------------------
// CLI
// ------------------------------

#ifndef LOGICA_PARSE_LIBRARY

static std::string ReadAllStdin() {
  std::ostringstream oss;
  oss << std::cin.rdbuf();
  return oss.str();
}

static std::string ReadFile(const std::string& path) {
  std::ifstream f(path);
  if (!f) {
    throw std::runtime_error("Failed to open file: " + path);
  }
  std::ostringstream oss;
  oss << f.rdbuf();
  return oss.str();
}

int main(int argc, char** argv) {
  try {
    std::string path = "-";
    bool full = false;
    bool use_file_name = false;

    for (int i = 1; i < argc; ++i) {
      std::string_view a(argv[i]);
      if (a == "--full") {
        full = true;
      } else if (a == "--use-file-name") {
        use_file_name = true;
      } else if (a == "-h" || a == "--help") {
        std::cout << "Usage: logica_parse_cpp [--full] [file|-]\n";
        std::cout << "Options:\n";
        std::cout << "  --full          Print full ParseFile() object (not just ['rule']).\n";
        std::cout << "  --use-file-name Treat input path as file_name (enables per-file predicate prefixing).\n";
        std::cout << "\n";
        std::cout << "Environment:\n";
        std::cout << "  LOGICAPATH=dir[:dir...]  Search path for imports (same as python logica.py).\n";
        return 0;
      } else {
        path = std::string(a);
      }
    }

    std::string content = (path == "-" ? ReadAllStdin() : ReadFile(path));

    std::vector<std::string> import_root;
    if (const char* lp = std::getenv("LOGICAPATH")) {
      std::string s(lp);
      size_t start = 0;
      while (start <= s.size()) {
        size_t pos = s.find(':', start);
        if (pos == std::string::npos) pos = s.size();
        std::string part = s.substr(start, pos - start);
        if (!part.empty()) import_root.push_back(part);
        start = pos + 1;
      }
    }

    // Match python logica.py parse: it calls ParseFile(program_text, import_root=...) with default file_name.
    // That means no per-file prefixing is applied to the top-level file.
    std::string file_name = use_file_name ? (path == "-" ? std::string("/dev/stdin") : path) : std::string("main");
    logica::parser::Json parsed = logica::parser::ParseFile(content, file_name, import_root);

    if (full) {
      std::cout << parsed.ToString(true, 1) << "\n";
    } else {
      const auto& obj = parsed.as_object();
      auto it = obj.find("rule");
      if (it == obj.end()) {
        std::cout << "[]\n";
      } else {
        std::cout << it->second.ToString(true, 1) << "\n";
      }
    }
    return 0;
  } catch (const logica::parser::ParsingException& e) {
    e.ShowMessage();
    return 1;
  } catch (const std::exception& e) {
    std::cerr << "Error: " << e.what() << "\n";
    return 1;
  }
}

#endif  // LOGICA_PARSE_LIBRARY
