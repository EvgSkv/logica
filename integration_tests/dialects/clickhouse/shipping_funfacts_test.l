#
# Copyright 2026 Google LLC
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

# A creative ClickHouse integration test exercising:
# - Records + field access (r.from / r.to)
# - Aggregations (+=, Count=, ArgMax=)
# - Deterministic ordering of output

@Engine("clickhouse");

# --- Universe: The Astra Freight Guild ---

Planet(name: "Astra",    sector: "Core");
Planet(name: "Borealis", sector: "Rim");
Planet(name: "Cygnus",   sector: "Core");
Planet(name: "Draco",    sector: "Rim");
Planet(name: "Erebus",   sector: "Void");

Ship(name: "Kestrel",  captain: "Mira");
Ship(name: "Orchid",   captain: "Jae");
Ship(name: "Nomad",    captain: "Sol");
Ship(name: "Pioneer",  captain: "Rin");

Crew(ship: "Kestrel", member: "Mira");
Crew(ship: "Kestrel", member: "Ivo");
Crew(ship: "Kestrel", member: "Tala");

Crew(ship: "Orchid", member: "Jae");
Crew(ship: "Orchid", member: "Kato");

Crew(ship: "Nomad", member: "Sol");
Crew(ship: "Nomad", member: "Uma");
Crew(ship: "Nomad", member: "Bea");
Crew(ship: "Nomad", member: "Nox");

Crew(ship: "Pioneer", member: "Rin");

# Shipment(id:, ship:, from:, to:, weight:, day:)
Shipment(id:  1, ship: "Kestrel", from: "Astra",    to: "Borealis", weight: 12, day: 1);
Shipment(id:  2, ship: "Kestrel", from: "Astra",    to: "Cygnus",   weight:  7, day: 1);
Shipment(id:  3, ship: "Orchid",  from: "Cygnus",   to: "Astra",    weight:  9, day: 1);
Shipment(id:  4, ship: "Nomad",   from: "Draco",    to: "Borealis", weight: 18, day: 1);
Shipment(id:  5, ship: "Pioneer", from: "Erebus",   to: "Astra",    weight:  3, day: 1);

Shipment(id:  6, ship: "Nomad",   from: "Borealis", to: "Astra",    weight: 14, day: 2);
Shipment(id:  7, ship: "Orchid",  from: "Astra",    to: "Draco",    weight:  7, day: 2);
Shipment(id:  8, ship: "Kestrel", from: "Cygnus",   to: "Erebus",   weight:  4, day: 2);
Shipment(id:  9, ship: "Nomad",   from: "Draco",    to: "Cygnus",   weight: 12, day: 2);
Shipment(id: 10, ship: "Pioneer", from: "Erebus",   to: "Borealis", weight:  9, day: 2);

Shipment(id: 11, ship: "Kestrel", from: "Astra",    to: "Borealis", weight:  6, day: 3);
Shipment(id: 12, ship: "Orchid",  from: "Borealis", to: "Draco",    weight:  2, day: 3);
Shipment(id: 13, ship: "Nomad",   from: "Cygnus",   to: "Astra",    weight: 16, day: 3);
Shipment(id: 14, ship: "Nomad",   from: "Cygnus",   to: "Draco",    weight:  1, day: 3);
Shipment(id: 15, ship: "Pioneer", from: "Astra",    to: "Erebus",   weight:  2, day: 3);

Shipment(id: 16, ship: "Kestrel", from: "Draco",    to: "Borealis", weight: 10, day: 4);
Shipment(id: 17, ship: "Orchid",  from: "Astra",    to: "Cygnus",   weight:  3, day: 4);
Shipment(id: 18, ship: "Nomad",   from: "Borealis", to: "Cygnus",   weight: 10, day: 4);
Shipment(id: 19, ship: "Pioneer", from: "Erebus",   to: "Draco",    weight:  8, day: 4);

# --- Derived metrics (aggregation syntax) ---

Outgoing(planet: p, total? += w) distinct :- Shipment(from: p, weight: w);
Incoming(planet: p, total? += w) distinct :- Shipment(to: p, weight: w);

PartnerCount(planet: p, n? Count= dest) distinct :- Shipment(from: p, to: dest);

RouteWeight(route: r, total? += w) distinct :-
  Shipment(from: f, to: t, weight: w),
  r = {from: f, to: t};

DayWeight(day: d, total? += w) distinct :- Shipment(day: d, weight: w);

CrewCount(ship: s, crew? Count= m) distinct :- Crew(ship: s, member: m);
ShipWeight(ship: s, total? += w) distinct :- Shipment(ship: s, weight: w);

ShipEfficiency(ship: s, eff: eff) :-
  ShipWeight(ship: s, total: total),
  CrewCount(ship: s, crew: crew),
  eff = total / crew;

# --- Winners (aggregation operators) ---

HubPlanet() ArgMax= p -> n :- PartnerCount(planet: p, n: n);
BusiestDay() ArgMax= d -> total :- DayWeight(day: d, total: total);
HeaviestRoute() ArgMax= r -> total :- RouteWeight(route: r, total: total);
BestShip() ArgMax= s -> eff :- ShipEfficiency(ship: s, eff: eff);

MostOutgoingPlanet() ArgMax= p -> w :- Outgoing(planet: p, total: w);
MostIncomingPlanet() ArgMax= p -> w :- Incoming(planet: p, total: w);

# --- Fun facts output ---

@OrderBy(FunFact, "kind", "subject");

FunFact(kind: "Hub planet", subject: p, value: ToString(n) ++ " destinations") :-
  p = HubPlanet(),
  PartnerCount(planet: p, n: n);

FunFact(kind: "Busiest day", subject: ToString(d), value: ToString(w) ++ " total tons") :-
  d = BusiestDay(),
  DayWeight(day: d, total: w);

FunFact(kind: "Heaviest route", subject: r.from ++ " -> " ++ r.to, value: ToString(w) ++ " tons") :-
  r = HeaviestRoute(),
  RouteWeight(route: r, total: w);

FunFact(kind: "Most outgoing", subject: p, value: ToString(w) ++ " tons shipped") :-
  p = MostOutgoingPlanet(),
  Outgoing(planet: p, total: w);

FunFact(kind: "Most incoming", subject: p, value: ToString(w) ++ " tons received") :-
  p = MostIncomingPlanet(),
  Incoming(planet: p, total: w);

FunFact(kind: "Best ship", subject: s ++ " (captain " ++ cap ++ ")", value: ToString(eff) ++ " tons/crew") :-
  s = BestShip(),
  Ship(name: s, captain: cap),
  ShipEfficiency(ship: s, eff: eff);

Test := FunFact();
