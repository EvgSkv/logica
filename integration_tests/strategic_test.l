#
# Copyright 2025 Google LLC
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


@Engine("duckdb", clingo: {time_limit: ∞, models_limit: 100, models_limit_soft: false});

ProdBy("meat", "Northern Butcheries", "Southern Grind");
ProdBy("cabbage", "Peaceful Joe", "Peaceful Joe");
ProdBy("spacetravel", "Stargazer", "Stargazer");
ProdBy("toys", "Toys Unlimited", "Gonzaga Toys");
ProdBy("shovels", "Open Kopai", "AlphaShovel");

ContrBy("Northern Butcheries", "Southern Grind", "Peaceful Joe", "Stargazer");
ContrBy("Toys Unlimited", "Stargazer", "Stargazer", "Stargazer");
ContrBy("Gonzaga Toys", "Open Kopai", "AlphaShovel", "Stargazer");

Company(c) :- ProdBy(x, y, z), c in [y, z];

Control(c) couldbe :- Company(c);

LackingProduct() cantbe :-
  ProdBy(p, x, y), ~Control(x), ~Control(y);
LackingControl() cantbe :-
  ContrBy(c, x, y, z),
  Control(x), Control(y), Control(y), ~Control(c);

Models() = Clingo(["ProdBy", "ContrBy", "Company", "Control",
                   "LackingProduct", "LackingControl"], []);

ControlInModel(company, model_id:) :-
  ExtractClingoCall(company, predicate: "Control", model_id:) = Models();

CompaniesInModel(model_id) List= company :-
  ControlInModel(company, model_id:);

Subset(c1, c2) :-
  Size(Set{x :- x in c1 ++ c2}) == Size(c2);

DefeatedModel(model_id) :-
  c1 = CompaniesInModel(model_id),
  c2 = CompaniesInModel(other_model),
  model_id != other_model,
  Subset(c2, c1);

MinimalModel(model_id) distinct :- ControlInModel(model_id:), ~DefeatedModel(model_id);

@OrderBy(StrategicInModel, "model_id", "col0");
StrategicInModel(company, model_id:) :-
  ControlInModel(company, model_id:),
  MinimalModel(model_id);

Strategic(company:, num_models? += 1) distinct :-
  StrategicInModel(company, model_id:);

@OrderBy(Test, "company", "num_models");
Test(company:, num_models:) :- Strategic(company:, num_models:);