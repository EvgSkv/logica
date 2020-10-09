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

@Engine("sqlite");

Office(city: "Kirkland", state: "Washington");
Office(city: "Seattle", state: "Washington");
Office(city: "Los Angeles", state: "California");

Employee(name: "A", city: "Kirkland");
Employee(name: "B", city: "Seattle");
Employee(name: "C", city: "Kirkland");
Employee(name: "D", city: "Los Angeles");

State(state) distinct :- Office(state:);

@With(EmployeesInState);
EmployeesInState(state:, employee_count:) :-
  State(state),
  employee_count += (1 :- Employee(city:), Office(city:, state:));

Test(..r) :- EmployeesInState(..r);
