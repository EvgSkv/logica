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

# Testing inner and outer joins.

@Engine("trino");

Phone(name: "John", phone: "123");
Phone(name: "James", phone: "345");
Phone(name: "Matthew", phone: "456");
Phone(name: "Joseph", phone: "567");

GetPhone(name) = phone :-
  phone AnyValue= (x :- Phone(name:, phone: x));

Email(name: "James", email: "james@example.com");
Email(name: "Matthew", email: "matt@example.com");
Email(name: "Timothy", email: "tim@example.com");

GetEmail(name) = email :-
  email AnyValue= (x :- Email(name:, email: x));

Person(name:) distinct :-
  Phone(name:) | Email(name:);

@OrderBy(CompleteContacts, "name");
CompleteContacts(name:, phone:, email:) :-
  Phone(name:, phone:), Email(name:, email:);

@OrderBy(Contacts, "name");
Contacts(name:, phone:, email:) :-
  Person(name:),
  phone == GetPhone(name),
  email == GetEmail(name);

Test("CompleteContacts", name:, phone:, email:) :-
  CompleteContacts(name:, phone:, email:);
Test("Contacts", name:, phone:, email:) :-
  Contacts(name:, phone:, email:);