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

# Example of modifying a value inside a repeated field within a repeated field.
# Input: Country. (defined below).
# Main predicate: BetterCountry, which is equal to Country, except for anyone
# who wanted have got a new washer and doesn't want a new washer any more.

@Engine("bigquery");

@OrderBy(BetterCountry, "col0.name");
BetterCountry(better_country) :-
  Country(country),
  better_country == MakeCountryBetter(country);

MakeCountryBetter(country) = {
  name: country.country_name,
  cities: MakeCitiesBetter(country.cities)
};

MakeCitiesBetter(cities) = (
  combine Array= better_city.key -> better_city :-
    better_city == MakeCityBetter(city),
    city in cities
);

MakeCityBetter(city) = {
  name: city.name,
  key: city.name,  # For list sorting.
  population: MakePopulationBetter(city.population)
};

MakePopulationBetter(population) = (
  combine Array= happier_person.key -> happier_person :-
    happier_person == MakePersonHappier(person),
    person in population
);

MakePersonHappier(person) = {
  name: person.name,
  key: person.name,  # For list sorting.
  dishwasher: person.dishwasher,
  washer: (
    if person.wants_new_washer  then
      "new " ++ person.washer
    else
      person.washer
  ),
  wants_new_washer: false
};


# Some fake data.
Country(
  {country_name: "USA",
   cities: [{
     name: "Seattle",
     population: [
       {
         name: "John",
         dishwasher: "Bosh",
         washer: "Samsung",
         wants_new_washer: false
       },
       {
         name: "James",
         dishwasher: "Samsung",
         washer: "Indesit",
         wants_new_washer: true
      }
     ]}, {
     name: "Chicago",
     population: [
       {
         name: "Maria",
         dishwasher: "Bosh",
         washer: "Samsung",
         wants_new_washer: true
       },
       {
         name: "Cleopatra",
         dishwasher: "Samsung",
         washer: "Indesit",
         wants_new_washer: false
       }
     ]}
   ]});
Country(
  {country_name: "Canada",
   cities: [{
     name: "Vancouver",
     population: [
       {
         name: "Jean",
         dishwasher: "Bosh",
         washer: "Samsung",
         wants_new_washer: true
       }
     ]
   }]});
