#
# Copyright 2023 Google LLC
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

# Testing that SQL string can be used as a table.
# Please never use it this way.
# This feature is provided for Spanner indexes specification.

@Engine("sqlite", type_checking: false);

Books() = [
    {
        book_name: "The Hobbit",
        author: "J.R.R. Tolkien"
    },
    {
        book_name: "The Lord of the Rings",
        author: "J.R.R. Tolkien"
    },
    {
        book_name: "Harry Potter and the Philosopher's Stone",
        author: "J.K. Rowling"
    },
    {
        book_name: "Harry Potter and the Deathly Hallows",
        author: "J.K. Rowling"
    },
    {
        book_name: "1984",
        author: "George Orwell"
    },
    {
        book_name: "Animal Farm",
        author: "George Orwell"
    }
];

OrwellBooks() Array= i -> book :-
  books == Books(),
  i in Range(Size(books)),
  book == books[i],
  book.author == "George Orwell";

# Running via index for subcription testing purposes.
NameAndAuthor() List=
    books[i].book_name ++ " and " ++ books[j].book_name ++
    " by " ++ books[i].author :-
  books == Books(),
  i in Range(Size(books)),
  j in Range(i),
  books[i].author == books[j].author;

A2d() Array= row_index -> row :-
  row_index in Range(5),
  row Array= (element_index -> element :-
              element_index in Range(4),
              element == 10 * row_index + element_index);

FromMatrix() = [{a23: a[2, 3],
                 a41: a[4, 1],
                 a11: a[1, 1]}] :- a == A2d();

Test("OrwellBooks", OrwellBooks());
Test("NameAndAuthor", NameAndAuthor());
Test("FromMatrix", FromMatrix());
