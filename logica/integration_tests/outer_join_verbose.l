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

# Outer join without mult-body-aggregation.

Phones(person: "Peter", phone: "4251112222");
Phones(person: "John", phone: "4251113333");
Emails(person: "John", email: "john@salem.org");
Emails(person: "James", email: "james@salem.org");

PersonPhonesAndEmailsNonAggregated(person:,
                                   phones: [phone],
                                   emails: []) :- Phones(person:, phone:);
PersonPhonesAndEmailsNonAggregated(person:,
                                   phones: [],
                                   emails: [email]) :- Emails(person:, email:);
PersonPhonesAndEmails(person:,
                      phones? ++= phones,
                      emails? ++= emails) distinct :-
  PersonPhonesAndEmailsNonAggregated(person:, phones:, emails:);

@OrderBy(PersonPhoneAndEmail, "person", "DESC");
PersonPhoneAndEmail(person:, phone:, email:) :-
  PersonPhonesAndEmails(person:, phones:, emails:),
  phone == If(Size(phones) == 1, Element(phones, 0), null),
  email == If(Size(emails) == 1, Element(emails, 0), null);
