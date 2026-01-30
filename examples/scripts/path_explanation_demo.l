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

# Explainable paths demo: "why does A depend on B?"
#
# We compute a shortest witness path as an array of nodes.

Depends("frontend", "api");
Depends("api", "billing");
Depends("billing", "payments_db");
Depends("api", "events");
Depends("events", "analytics");

# Shortest path search (same pattern as integration_tests/sqlite_reachability.l).
Path(source:, target:, length? Min= 1, path? ArgMin= ([source] -> 1)) distinct :-
  Depends(source, target);

Path(source: a, target: c,
     length? Min= l1 + l2,
     path? ArgMin= ArrayConcat(p1, p2) -> (l1 + l2)) distinct :-
  Path(source: a, target: b, length: l1, path: p1),
  Path(source: b, target: c, length: l2, path: p2);

Explain(source:, target:, witness_path:) :-
  Path(source:, target:, path: p),
  witness_path == ArrayConcat(p, [target]),
  source != target;

# One concrete "why" question.
WhyFrontendToDb(witness_path) :-
  Explain(source: "frontend", target: "payments_db", witness_path: witness_path);

Q(source:, target:, witness_path:) :-
  Explain(source:, target:, witness_path:);
