#!/usr/bin/python
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

# Example of performing outer joins.

# Example data.
Phone(name: "John", phone: "123");
Phone(name: "James", phone: "345");
Phone(name: "Matthew", phone: "456");
Phone(name: "Joseph", phone: "567");
Email(name: "James", email: "james@example.com");
Email(name: "Matthew", email: "matt@example.com");
Email(name: "Timothy", email: "tim@example.com");

# Determining the keys in the full outer join table.
Person(name:) distinct :-
  Phone(name:) | Email(name:);

# Writing functions for retrieving an outer joined
# record if one exists.
GetPhone(name) = phone :-
  phone AnyValue= (x :- Phone(name:, phone: x));
GetEmail(name) = email :-
  email AnyValue= (x :- Email(name:, email: x));

# Running full outer join.
@OrderBy(Contacts, "name");
Contacts(name:, phone:, email:) :-
  Person(name:),
  phone == GetPhone(name),
  email == GetEmail(name);

# Running left join.
ContactsOfPeopleWithPhone(name:, phone:,
                          email: GetEmail(name)) :-
  Phone(name:, phone:);
