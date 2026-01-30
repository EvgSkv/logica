#!/usr/bin/env logica
#
# Copyright 2026 Logica Authors
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

@Engine("sqlite");

# A tiny demo of "team contracts": promises vs requirements.
# The output is a list of objectively checkable violations.

Team("billing");
Team("risk");
Team("analytics");

System("charge_api");
System("events_stream");

Owns("billing", "charge_api");
Owns("analytics", "events_stream");

# Promises: what the owner team claims to provide.
# Example: latency_p95_ms <= 200
PromiseSla("billing", "charge_api", "latency_p95_ms", 200);
PromiseSla("analytics", "events_stream", "delivery_lag_p95_s", 60);

# Requirements: what a consumer team needs.
NeedSla("risk", "charge_api", "latency_p95_ms", 150);
NeedSla("billing", "events_stream", "delivery_lag_p95_s", 10);

# Schema promises/requirements (simplified).
PromiseFieldType("billing", "charge_api", "amount", "Int64");
NeedFieldType("risk", "charge_api", "amount", "Float64");

# Violations.
SlaViolation(consumer, owner, system, metric, need, promise) :-
  NeedSla(consumer, system, metric, need),
  Owns(owner, system),
  PromiseSla(owner, system, metric, promise),
  need < promise;

MissingPromise(consumer, owner, system, metric, need) :-
  NeedSla(consumer, system, metric, need),
  Owns(owner, system),
  ~PromiseSla(owner, system, metric, _);

TypeViolation(consumer, owner, system, field, need_type, promise_type) :-
  NeedFieldType(consumer, system, field, need_type),
  Owns(owner, system),
  PromiseFieldType(owner, system, field, promise_type),
  need_type != promise_type;

Q(kind, consumer, owner, system, subject, expected, actual) :-
  SlaViolation(consumer, owner, system, metric, need, promise),
  kind == "sla",
  subject == metric,
  expected == ToString(need),
  actual == ToString(promise);

Q(kind, consumer, owner, system, subject, expected, actual) :-
  MissingPromise(consumer, owner, system, metric, need),
  kind == "missing_promise",
  subject == metric,
  expected == ToString(need),
  actual == "(no promise)";

Q(kind, consumer, owner, system, subject, expected, actual) :-
  TypeViolation(consumer, owner, system, field, need_type, promise_type),
  kind == "type",
  subject == field,
  expected == need_type,
  actual == promise_type;

@OrderBy(Q, "col0");
