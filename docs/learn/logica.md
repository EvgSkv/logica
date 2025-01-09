# Logica: from facts to functors

## Introduction

Logica is a logic programming language developed for streamlined data processing and analysis.

Logica programs compile to SQL thus leveraging power of SQL ecosystem for Logic Programming.
Thus Logica is powered by modern data engines, it runs on SQLite, Postgres, BigQuery and DuckDB.

While connection between database engines and first order logic is well known and is actively used in
academic research, control of the engines is performed primarily with SQL (Structured English Query Language).

Languages directly based on the first order logic syntax (Prolog, Datalog) are studied academically
and are used in database research, but have applied usage that is minor compared to SQL.

Decision to base SQL on natural language have opened it to a wide population of users.
Relational databases have saved humanity a lot of time and effort.
However there is a reason that mathematicians use special notation.
Popular imperative programming languages are heavily based on functional notation from mathematics.
Special notation helps, and for complex programs, like the ones solved that data scientists and engineers,
special notation helps a lot.

Logic program is a collection of statements. Each statement is a fact or a rule.

Consider an example:
_Socrates is a human. Humans are mortal._

_Therefore Socrates is mortal._

What if we want to do this reasoning automatically?

Logica program describing this would be

```
Human("Socrates");
Mortal(x) :- Human(x);
```

To find out who is mortal we can run in shell

```
$ logica socrates.l run Mortal
```

This would result in the output:

```
+----------+
| col0     |
+----------+
| Socrates |
+----------+
```

> [!TIP]
> Logica by default uses BigQuery engine for exection of Logic programs. If you are eager
> to run your first logic program and you do not have BigQuery client installed please
> see section [Execution on SQL engines](#execution-on-sql-engines) for how to run your program
> on SQLite. Or continute reading and we promise that you will get to it in due time.

## Foundation

### Predicates

Predicate is a statement with variables. Application of predicate to a given variables/expressions/constants is called predicate call.

Example 1: Let `Parent(x, y)` stand for "x is a parent of y". Then:

* `Parent("Adam", "Abel")` is true.
* `Parent("Philip of Macedon", "Alexander of Macedon")` is true.
* `Parent("Philip of Macedon", "Julius Caesar")` is false.

Example 2: Let `NumLegs(x, y)` stand for "x has y legs." Then

* `NumLegs("cat", 4)` is true.
* `NumLegs("black widow spider", 4)` is false.

Logic program is a collection of _rules_. These rules define predicates.

### Facts

Simplest rules are facts. Facts simply state that a certain predicate holds (i.e. is true) for those values.

For example Logica program may state:
```
Parent("Adam", "Abel");
Parent("Philip of Macedon", "Alexander of Macedon");
```

In Logica you specify at execution time which predicate you would like to produce.
Thus to see table of parent relationship you would run:
```
$ logica socrates.l run Parent
```
and get
```
+-------------------+----------------------+
|       col0        |         col1         |
+-------------------+----------------------+
| Adam              | Abel                 |
| Philip of Macedon | Alexander of Macedon |
+-------------------+----------------------+
```

### Implications

Rules can specify how to derive new facts from known ones. These rules rules of derivation are called _implications_.

Implication has form: `<conclusion> :- <condition>`.

Implications state conditions under which a predicate holds for a tuple of values given that some predicates already hold for come tuples of values.

Example 1: To state "X is grandparent of Z if X is a parent of parent of Z." in Logica we would write:

```
Grandparent(x, z) :- Parent(x, y), Parent(y, z);
```

Example 2: To state "X is quadropod if it has 4 legs" in Logica we would write:

```
Quadropod(x) :- NumLegs(x, 4);
```

Example 3: x is sibling of y if they are children of the same parent.

```
Sibling(x, y) :- Parent(z, x), Parent(z, y);
```

Example 4: x is close relative of y if x is a parent, a child, or a sibling of y.

```
CloseRelative(x, y) :-
  Parent(x, y) |
  Parent(y, x) |
  (Parent(z, x), Parent(z, y));
```

Multiple rules for a predicate are allowed. Multiple rules are equivalent to a single rule which body is disjunction of bodies of those.

Example 5. Equivalent to _Example 4_.
"`x` is close relative of `y` if `x` is parent of `y`. `x` is close relative of `y` if `x` is child of `y`.
`x` is close relative of `y` if `x` is a sibling of `y`."

```
CloseRelative(x, y) :- Parent(x, y);
CloseRelative(x, y) :- Parent(y, x);
CloseRelative(x, y) :- Parent(z, x), Parent(z, y);
```

> [!NOTE]
>  Logica is case-sensitive and case is used for semantics:
> Variables are to be latin lower_case: `x`, `y`, `my_variable`.
> Predicates are to be CamelCase starting with capital: `P`, `Q`, `MyPredicate`

### Built-in operators

Arithmetic operators and comparison operators can be used in rules.

Example 1: Profit from a property is equal to revenue minus expenses.

```
PropertyProfit(property_id, revenue - expenses) :-
  PropertyRevenue(property_id, revenue),
  PropertyExpense(property_id, expense);
```

Example 2:  Profitable property is a property with positive profit.

```
Profitable(property_id) :-
  PropertyProfit(property_id, profit),
  profit > 0;
```

### Equality == Assignment

Logic Programming is declarative, and thus there is no difference between equality and assignment, operator == stands for both.

Example 1:

```
Grandparent(a, b) :-
  Parent(a, child_of_a), Parent(parent_of_b, b),
  child_of_a == parent_of_b;
```

Example 2:

```
Grandparent(x, y) :-
  Parent(a, b), Parent(b, c), x == a, y == c;
```

Assignment can be used to store results of intermediate computation.

Example 3: Compute volumes and mass of metal cubes.

```
# Arguments of MetalCube are cube name, side length and density.
MetalCube("cube1", 10, 15);
MetalCube("cube2", 20, 8);

CubeInfo(cube_id, volume, mass) :-
  MetalCube(cube_id, side, density),
  volume == side * side * side,
  mass == volume * density;
```

### Named arguments

Named arguments enable operations with tables with large number of columns and help with readability of output.

Example 1: Here are some facts about people of ancient Greece.

```
Human(name: "Socrates", iq: 250, year_of_birth: -470, location: "Athens");
Human(name: "Aristotle", iq: 240, year_of_birth: -384, location: "Athens");
Human(name: "Archimedes", iq: 245, year_of_birth: -287, location: "Syracuse");
Human(name: "Themistocles", iq: 130, year_of_birth: -524, location: "Athens");
```

When rendered as table names of arguments become column names. Predicate `Human` defined above would result in a table:

```
+--------------+-----+---------------+----------+
|     name     | iq  | year_of_birth | location |
+--------------+-----+---------------+----------+
| Socrates     | 250 |          -470 | Athens   |
| Aristotle    | 240 |          -384 | Athens   |
| Archimedes   | 245 |          -287 | Syracuse |
| Themistocles | 130 |          -524 | Athens   |
+--------------+-----+---------------+----------+
```

When calling a predicate with named arguments you only specify the ones that you need.

Example 2: AthenianPhilosopher is any person from Athens with an IQ greater than 200.

```
AthenianPhilosopher(philosopher:) :-
  Human(name: philosopher,
        location: "Athens", iq: iq),
  iq > 200;
```

With the facts from Example 1 we have `AthenianPhilosopher` evaluate to:

```
+-------------+
| philosopher |
+-------------+
| Socrates    |
| Aristotle   |
+-------------+
```

Often you will call a predicate with a positional argument extracting its value to a variable of 
the same name, like it happens with argument `iq` in the call
`Human(name: philosopher, location: "Athens", iq: iq)` in Example 2.
In these situations Logica allows a shorthand: simply skip the name of the variable.

Example 2: Equivalent to _Example 2_ using implicit variable name for argument `iq`.

```
AthenianPhilosopher(philosopher:) :-
  Human(name: philosopher,
        location: "Athens", iq:),
  iq > 200;
```

> [!NOTE]
> Positional arguments are internally interpreted as named arguments with names `col0`, `col1`, `col2`, etc.
> For example a call
> ```
> P(x, y, z)
> ```
> is equivalent to call
> ```
> P(col0: x, col1: y, col2: z)
> ```

### Value types

#### Basic types

Logica operates on numbers, strings, booleans and composite data types.

Numbers: `1`, `5`, `10`, `42`, `3.1415`, …

Strings: `"Hello World"`, `"Ekaterinburg"`, `"Athens"`, …

Booleans: `true`, `false`

All data types are _optional_, that is any variable or argument may be taking a special `null` value, which
roughly stands for stating that the value is missing. Value `null` occurs in aggregation which will be discussed in
the Aggregation section.

#### Composite types

Logica has two composite types: _arrays_ and _records_. A variable or argument of composite type can also be
taking `null` value.

##### Arrays

Words "list" and "array" are synonyms in Logica and can used interchangably.

Array is an ordered sequence of elements of the same type.

Syntax for lists is identical to Python: `[element1, element2, …]`

Example 1:

Person(name: "Victoria", children: ["Edward", "Leopold"]);
Person(name: "Edward", children: ["George V", "Maud"]);

Operator `in` makes a variable to run over elements of the list.

Example 2:

```
Centaur(x) :-
  x in ["Chiron",
        "Hylonome",
        "Dictys"];
```

is equivalent to

```
Centaur("Chiron");
Centaur("Hylonome");
Centaur("Dictys");
```

##### Records

A record is a data type that consists of one or many named fields. Each field stores an element of some data type.
Records are analogous to JSON objects, PostreSQL composite types, Google ProtoBuffers.
Record syntax is similar to JavaScript object syntax:
  ```{field_name_1: value_1, field_name_2: value_2, …}```

Field is addressed with usual syntax of `record_name.field_name`

Example 1:

```
Book(title: "To Kill a Mockingbird", 
     info: {author: "Harper Lee", publication_year: 1960});
Book(title: "1984", 
     info: {author: "George Orwell", publication_year: 1949});
Book(title: "The Great Gatsby", 
     info: {author: "F. Scott Fitzgerald", publication_year: 1925});

RecentBook(title:) :-
  Book(title:, info:),
  info.publication_year > 1950;
```

## Multiset Semantics

Logica, as well as most other logic programming languages follows multiset semantics.

That there is no ordering of rows in predicates, but 
each row may occur 1, or many times in the predicate.

Number of occurrences of a row is called _multiplicity_.

Example 1: Predicate `Fruit` defined with facts

```
Fruit("apple");
Fruit("apple");
Fruit("orange");
Fruit("banana");
Fruit("banana");
Fruit("banana");
```

evaluates to

```
+--------+
| col0   |
+--------+
| apple  |
| apple  |
| orange |
| banana |
| banana |
| banana |
+--------+
```

Disjunction sums multiplicities.

Example 2: Predicate `OurFruit` defined as

```
MyFruit("apple");
MyFruit("banana");

YourFruit("apple");
YourFruit("orange");

OurFruit(x) :- MyFruit(x) | YourFruit(x);
```

evaluates to

```
+--------+
|  col0  |
+--------+
| apple  |
| banana |
| apple  |
| orange |
+--------+
```


Conjunction multiplies multiplicities.

To illustrate the concept we will use an abstract predicate this time.

Example 3: Predicate `Q` defined as

```
Q("a", "b");
Q("a", "b");
Q("x", "y");

R("b", "t");
R("b", "t");
R("b", "t");

P(x, z) :- Q(x, y), R(y, z);
```

evaluates to

```
+------+------+
| col0 | col1 |
+------+------+
| a    | t    |
| a    | t    |
| a    | t    |
| a    | t    |
| a    | t    |
| a    | t    |
+------+------+
```

Multiset semantics is natural for applications.

Disjunction is anaolgous to consequent for loops while conjunction is analogous to nested loops.

For example program 
```
C(x) :- A(x) | B(x);
```

acts like Python program

```
C = []
for x in A:
  C.append(x);
for x in B:
  C.append(x);
```

And program

```
C(x) :- A(x), B(x);
```

Acts like:

```
C = []
for x1 in A:
  for x2 in B:
    if x1 == x2:
      C.append(x1)
```


## Execution on SQL engines

Logica is native to SQL ecosystem, it is designed to compile to SQL and run on data
that customer already has in their database. As of May 2024 Logica runs on BigQuery, SQLite and PostgreSQL.
In this guide we will be using SQLite. It is a highly efficient free database that is onmipresent
and in particular is part of Python standard library.

To specify that you would like to run your Logica program in SQLite include line `@Engine("sqlite");`
in your program. For example you could write.

```
@Engine("sqlite");
Human("Socrates");
Mortal(x) :- Human(x);
```

Now you can find out who is mortal with command

```
$ logica socrates.l run Mortal
```

and it will run with built-in SQLite engine.

The line `@Engine("sqlite");` that you have added looks like a fact and it is. The predicate here is `@Engine`.
Special predicates that start with `@Engine` are called _imperatives_. The predicates are used to
command to the Logica engine on what to do.

### Connecting and reading from database

By default when running on SQLite Logica connects to in-memory database. If you want to connect to an existing
file use `@AttachDatabase` imperative, which you give database alias and database filename. Use `logica_home`
alias to use this database by default. Any undefined predicate that you call is interpreted by Logica
to be an existing table in the database. So if you have a table called `employee` with column `name` and `salary`
in your SQLite database file `i_learn_logica.db`, then predicate `WellPaidEmployee` defined as such will hold
well paid employees.

```
# File: find_well_paid.l
@Engine("sqlite");
@AttachDatabase("logica_home", "i_learn_logica.db");
WellPaidEmployee(name:) :- employee(name:, salary:), salary > 1000;
```

Run this program as usual.

```
python3 -m logica find_well_paid.l run WellPaidEmployee
```

### Writing to database

To write to a database use imperative `@Ground(P)`. Logica will write _grounded_
predicate `P` when you evalute a predicate that depends on `P`.

Consider a program `test_saving.l`.
```
@Engine("sqlite");
@AttachDatabase("logica_home", "wall.db");

@Ground(T);
T("mene");
T("mene");
T("tekel");
T("upharsin");

S() += 1 :- T();
```

Predicate `T` is commanded to be grounded and predicate `S` simply counts the number of rows of `T`.

When you run `python3 -m logica test_saving.l run S` you will see that `S` has 4 rows and predicate `T` will
be written to table `T` in database `wall.db`.

Running  `python3 -m logica test_saving.l run T` will simply show you what Belshazzar has read on the wall without
affecting the database. That is Logica saves grounded intermediates and does not save a predicate if user
asked to print it directly.

> [!TIP]
> If you want your program to write multiple predicates to the database, then define an
> auxiliary predicate that counts the total number of rows in all the predicates that
> you want to write. For example if you want predicates `A`, `B` and `C` be written then
> define in your program
>
> ```
> # File: my_workflow.l
> Workflow() += 1 :- A() | B() | C();
> ```
>
> and run `python3 -m logica my_workflow.l run Workflow`.

## Aggregation

There are two types of aggregation in Logica: predicate-level
aggregation and aggregating expressions.

### Predicate-level aggregation

For our purposes we define set to be a multiset with multiplicity of all
occuring rows to be exactly 1. Predicate-level aggregation allows building sets.

Use `distinct` keyword in the head of the rule to make the rule aggregating.
Aggregating rules always produce predicates that correspond to sets, thus the
choice of `distinct` keyword: all the rows in resulting tables are distinct.

Let us consider a predicate `FruitPurchase` which tells which fruits of which weights
we purchased. Say it is defined with the following facts:

```
FruitPurchase(fruit: "apple", weight: 0.5);
FruitPurchase(fruit: "apple", weight: 0.4);
FruitPurchase(fruit: "orange", weight: 0.6);
FruitPurchase(fruit: "orange", weight: 0.4);
FruitPurchase(fruit: "orange", weight: 0.5);
FruitPurchase(fruit: "pineapple", weight: 0.9);
FruitPurchase(fruit: "pineapple", weight: 1.1);
```

Now sat we need to define predicate `Fruit(fruit:)` that would list all the fruits mentioned
by `FruitPurchase` exactly once. Have we defined it as `Fruit(fruit:) :- FruitPurchase(fruit:)`
we would have multiplicities of each fruit equal to its multiplicity in the original table.
To define the set we se keyword `distinct` as follows:

```
Fruit(fruit:) distinct :- FruitPurchase(fruit:);
```

Now `Fruit` would evaluate to

```
+-----------+
| fruit     |
+-----------+
| apple     |
| orange    |
| pineapple |
+-----------+
```

Aggregating predices are also allowed to have aggregating arguments, which would not simply
be values computed by the body, but aggregations of such values. Unlike regular arguments specified as `<argument_name>: <argument_value>` the aggregating arguments are specified
as `<argument_name>? <AggregatingOperator>= <aggregated_value>`.

For example if we wanted to compute total weight maximal weights of each type of purchased fruit we could do it with `+` and `Max` aggregating operators as follows:

```
Fruit(fruit:,
      total_weight? += weight,
      maximal_weight? Max= weight) distinct :- FruitPurchase(fruit:, weight:);
```

This would evaluate to

```
+-----------+--------------+----------------+
| fruit     | total_weight | maximal_weight |
+-----------+--------------+----------------+
| apple     | 0.9          | 0.5            |
| orange    | 1.5          | 0.6            |
| pineapple | 2.0          | 1.1            |
+-----------+--------------+----------------+
```

Special value `null` is ignored by all built-in aggregating operators. So, for example, having an a fact
`FruitPurchase(fruit: "apple", weight: null);` would have no impact on the output.

Aggregating functions `ArgMax` and `ArgMin` allow for selection of a key with the largest value.
These predicate aggregate key-value pairs. A key-value pair in Logica is represented as a
record `{arg:, value:}`. Infix operator `->` constructs such record.

For example predicate `Q` defined as
```
Q("apple" -> 2);
Q("banana" -> 4);
Q("cantaloupe" -> 6);
```

evaluates to

```
+--------------------------------+
| col0                           |
+--------------------------------+
| {"arg":"apple","value":2}      |
| {"arg":"banana","value":4}     |
| {"arg":"cantaloupe","value":6} |
+--------------------------------+
```

So to pick key corresponding to maximum value apply `ArgMax` aggregation operation to `key -> value` pair.
Example: Selecting wisest person in each city.

```
Human(name: "Socrates", iq: 250, year_of_birth: -470, location: "Athens");
Human(name: "Aristotle", iq: 240, year_of_birth: -384, location: "Athens");
Human(name: "Archimedes", iq: 245, year_of_birth: -287, location: "Syracuse");
Human(name: "Themistocles", iq: 130, year_of_birth: -524, location: "Athens");

WisestHuman(city:, person? ArgMax= name -> iq) distinct :-
  Human(name:, iq:, location: city);
```

### Aggregating expressions

Aggregating expressions of Logica are similar to mathematical 
[Set builder](https://en.wikipedia.org/wiki/Set-builder_notation#Sets_defined_by_a_predicate) notation,
but they allow combining elements with an arbitrary aggregating function.

You can call aggregating operator on a multiset using figure parenthesis:
` <AggregatingOperator>{<aggregated value> :- <proposition>)}`.

For example let us assume we have a predicate `Purchase` which holds information about movie ticket purchases, in particular it has
argument `purchase_id` with the id of the purchase entry and `ticket` holding a list of tickets.

Example 1: Finding total purchase value and most expensive tickets.

```
PurchaseSummary(purchase_id:, total_value:, most_expensive:) :-
  Purchase(purchase_id:, tickets:),
  total_value = Sum{ticket.price :- ticket in tickets},
  most_expensive = Max{ticket.price :- ticket in tickets};
```

#### List comprehension

Using `List` aggregation operator enables the use of aggregating expressions as list comprehensions.

Example 3: For each purchase keep only expensive tickets.

```
ExpensiveTickets(purchase_id:, expensive_tickets:) :-
  Purchase(purchase_id:, tickets:),
  expensive_tickets = List{ticket :- ticket in tickets, ticket.price > 100};

```

#### Outer joins

Aggregating expressions can be used to look up information, which serves the same purpose as _outer joins_ in SQL.

Example 4: Assemble phones and emails of people in a single table.

```
PeopleContacts(person:, emails:, phones:) :-
  Person(person),
  emails = List{email :- PersonEmail(person:, email:)},
  phones = List{phone :- PersonPhone(person:, phone:)};
```

#### Aggregating nothing to `null`

When proposition of the aggregating expressions is not satisfied by any values then
built-in aggregating operators result in a `null`.

So for instance if for some person from Example 4 there were no emails found then
`emails` argument would be equal to `null` in their row.

You can check if some value is null using `is` operator. As Logica compiles to SQL you can
not use `==` for checking if a value is `null`.

For instance the following rule can be used to find people who has no emails listed.

```
PersonWithNoEmails(person) :-
  PeopleContacts(person:, emails:), emails is null;
```

#### Negation as an aggregating expression

To negate a proposition use `~` operator. This operator stands for an aggregating expression.
Consider a set of facts

```
Bird("sparrow");
Bird("eagle");
Bird("canary");
Bird("cassowary");

CanFly("sparrow");
CanFly("eagle");
CanFly("canary");

CanSing("sparrow");
CanSing("canary");
CanSing("cassowary");
```

and lets say we want to find all birds that can sing, but can not fly. It can be done
with the following rule.

```
InterestingBird(x) :-
  Bird(x), CanSing(x), ~CanFly(x);
```

Logica interprets negation in this rule as follows:

```
InterestingBird(x) :-
  Bird(x), CanSing(x), Max{1 :- CanFly(x)} is null;
```

Indeed aggregating expression `Max{1 :- CanFly(x)}` will be aggregating over a non-empty
multiset of `1` values if and only if proposition `CanFly(x)` holds, and would run over an empty
set otherwise, resulting in a `null`. 

> [!NOTE]
> Inquisitive reader may have observed that any other built-in
> aggregating operator could have worked here, e.g. we could have used `Sum{42 :- CanFly(x)}`
> with the same outcome.

## Computation

We have described Logica's declarative syntax and semantics. But how can the predicates be
evaluated to concrete tables?

### Concrete predicates

Logica predicate is called _concrete_ if it is being evaluated to a specific table of values. All predicates
that we defined so far were concrete, they were either defined by a collection of facts, or finite
multisets computable from other predicates. In particular see `Fruit`, `Book` or `RecentBook` above.

### Injectible predicates

Injectible predicates are predicates that perform calculation of some of it's arguments based on other
arguments which are provided as input.

Example: Computing adjusted employee salary using an auxiliary predicate.

```
Employee(name: "Alice", salary: 50000);
Employee(name: "Bob", salary: 60000);
Employee(name: "Charlie", salary: 55000);

AdjustedSalary(employee_salary, increase_percent, new_salary) :-
  new_salary == employee_salary * (1 + increase_percent / 100);

EmployeeSalaryIncrease(name:, adjusted_salary:) :-
  Employee(name:, salary:),
  AdjustedSalary(salary, 10, adjusted_salary);
```

In this example predicate `AdjustedSalary` could not be just printed out as a table. Mathematically
it is a set of triples, but this is an infinite set of triples (or very large if we consider finite
precision of floats) and it is not practical to represent it verbatim in memory or on disk.

However when we are evaluating concrete predicate `EmployeeSalaryIncrease` we can _inject_
 `AdjustedSalary`. Inject predicate means replace call to the predicate with its body.
 So in this case we replace
`AdjustedSalary(salary, 10, adjusted_salary)` with
`adjusted_salary == salary * (1 + 10 / 100)` and thus being able to compute `adjusted_salary`.

For a predicate to be injectible it must be defined with a signle non-aggregating conjunctive rule.



## Functional notation

Functions are mathematical objects that take some value as an input and return some value as an output.
Modern imperative programming language extensively use functions, and there is a whole programming
paradigm _functional programming_ that doubles down on using functions to express the computation.
Functions are indeed a conventient way to express data items transformation.

In mathematics functions are often defined as sets of pairs, where the first element is the input of
the function and the second element is the output. Logica follows the same path, allowing predicates
to be used as functions.

Let's consider a toy example, where our input data is defined by predicate `T` and consists of some numbers,
our tranformation is defined by a predicates `S` which squares the numbers and predicate `D` which doubles the
numbers. We obtain output data `R` applying those two transformations to each element of `T`.

```
T(1);
T(2);
T(5);
T(8);
T(9);

S(x, y) :- y == x * x;
D(x, y) :- y == 2 * x;

R(z) :-
  T(x),
  S(x, y);
  D(y, z);
```

To apply the sequence of transformations using regular predicates we need to introduce variables for intermediate
results. Composition of functions is more readable. Let us first see how we can implement the same computation
using functions in Logica and then discuss internal semantics.

```
T(1);
T(2);
T(5);
T(8);
T(9);

S(x) = x * x;
D(x) = 2 * x;

R(D(S(x))) :-
  T(x);
```

In general when a predicate is defined with functional value `= <functional value>` this value is simply
represented as a column named `logica_value: <functional value>`.

For example if we define a predicate

```
BookAuthor(title: "To Kill a Mockingbird", year: 1960) = "Harper Lee";
BookAuthor(title: "1984", year: 1949) = "George Orwell";
BookAuthor(title: "The Great Gatsby", year: 1925) = "F. Scott Fitzgerald";
BookAuthor(title: "Brave New World", year: 1932) = "Aldous Huxley";
BookAuthor(title: "Catch-22", year: 1961) = "Joseph Heller";
```

then it would be evaluating to

```
+-----------------------+------+---------------------+
|         title         | year |    logica_value     |
+-----------------------+------+---------------------+
| To Kill a Mockingbird | 1960 | Harper Lee          |
| 1984                  | 1949 | George Orwell       |
| The Great Gatsby      | 1925 | F. Scott Fitzgerald |
| Brave New World       | 1932 | Aldous Huxley       |
| Catch-22              | 1961 | Joseph Heller       |
+-----------------------+------+---------------------+
```

When defining functional predicates you have all the regular
arsenal available, i.e. you can have rule body, variables, named and
positional arguments etc.

For example if we already had `Book` predicate we could define
`BookAuthor` functional predicate as follows:

```
Book(title: "To Kill a Mockingbird", 
     info: {author: "Harper Lee", publication_year: 1960});
Book(title: "1984", 
     info: {author: "George Orwell", publication_year: 1949});
Book(title: "The Great Gatsby", 
     info: {author: "F. Scott Fitzgerald", publication_year: 1925});

BookAuthor(title:, year: info.publication_year) = info.author :-
  Book(title:, info:);
```

When functional predicate is used as function, its occurence is replaced with the
an auxiliary variable and call to the predicate is added conjunctively to extract
the value of this variable from `logica_value` column.

For example proposition

```F1(x) + 1 == F2(y) + 10```

is interpreted as a conjunction

```f1 + 1 == f2 + 10, F1(x, logica_value: f1), F2(y, logica_value: f2)```


## Bolean logic

There is a boolean type in Logica. Careful reader may have already concluded that there is a difference
between preicates and boolean funcitons in Logica.

Consider an example of a boolean function `SweetF` and a predicate `SweetP` that describe which of the foods
are sweet.

```
Food("salami");
Food("strawberry");
Food("cake");
Food("potato");

SweetF("samami") = false;
SweetF("strawberry") = true;
SweetF("cake") = true;
SweetF("potato") = false;

SweetP("strawberry");
SweetP("cake");
```

Predicate `SweetP` is to be used in propositions, while `SweetF` in expressions.

For example you can use `SweetF` to define predicate `FoodInfo` as follows.

```
FoodInfo(food:,
         food_is_sweet: SweetF(food_name));
```

Predicate `SweetF` in this formula is used to both retrieve `food_name` from its first positional
argument and the sweetness of food from its `logica_value` argument.

If you used `SweetP` in this context then you would get an error that there is no `logica_value` in
the predicate `SweetP`.

Consider an example of use of `SweetP` in a propsition.

```
SweetForLunch(food) :- Lunch(food), SweetP(food);
```

Using `SweetF` in this context would be incorrect, as in the proposition `SweetF` would work as a predicate
and any item that holds as `SweetF` first argument (which is all possible food) in our example would
pass. Argument `logica_value` would be ignored.

If you do want to use a boolean function for filterig then pass the result to a `Constratint` predicate.

```
SweetForLunch(food) :- Lunch(food), Constraint(SweetF(food));
```

or you can explicitly check for equality with `true`.

```
SweetForLunch(food) :- Lunch(food), SweetF(food) == true;
```


### Logica's special treatment of binary relations

For the sake of ergonomics Logica has special case treatment for binary relations such as
`==`, `<`, `<=` as well as for boolean operators `&&`, `||`, `!`.

So for instance you can use `<=` in both of these rules.

```
FifteenToNineteen(x) :- x in Range(20), x >= 15;

NumberInfo(number:, number_is_fifteen_to_nineteen: (x >= 15)) :-
  number in Range(20);
```

Operator `<=` is interpreted as a predicate in the first rule and performes filtering
and is interpreted as a boolean function in the second rule and will result
in `false` value for numbers below 15 and `true` value for numbers after 15.

This behavior is happening **only** for the operators and is not happening for
boolean functions built-in or not.

### Assignment operator `=`

A reader with previous background in a contentional programming launguage such as `C`, `Python`, `C++`, `Java` 
is probably used to a singular `=` sign being used as an assignment.

And luckily Logica does have a singular assignment operator `=` which works analogously to the way it does in `C`,
that is it returns the assigned value, unline `==` which returns boolean when used as a function.


Example 1: Using `=` in a proposition.

```
Cube(side: 10, density: 0.5);
Cube(side: 5, density: 2);

CubeInfo(side:, density:, volume:, mass:) :-
  Cube(side:, density:),
  volume = side * side * side,
  mass = volume * density;
```

In this example we may have used `==` with the same result.

> [!NOTE]
> When used in propostion opereators `=` and `==` exhibit identical behavior.

Whether ever using `=` to remember a value is good for readability is a matter
of taste and we leave it to the reader to make the choice.

Example 2: Using `=` as a function to remember assigned value.

```
Cube(side: 10, density: 0.5);
Cube(side: 5, density: 2);

CubeInfo(side:, density:, volume:, mass:) :-
  Cube(side:, density:),
  # This code reads "mass is the volue (which is a cube of a side) times density."
  mass = (volume = side * side * side) * density;
```

If you used `==` in instead of `=` in Example 2 expression `(volume = side * side * side)`
you would get an error because `==` as a boolean function works `(in, in) -> out` mode and thus
there is no assignment happening to volume.

### Using boolean expressions for efficiency

Anything that is done with boolean operations can be achieved with propositional conjunction and
disjunction. But using boolean operations leads to simpler evaluation strategy.

Example: Computing club membership eligibility. Person to be eligible must be at least 25 years old and
reside in New York or San Francisco.

```
Person(name: "Alice", age: 30, city: "New York");
Person(name: "Bob", age: 22, city: "San Francisco");
Person(name: "Charlie", age: 35, city: "Los Angeles");
Person(name: "Diana", age: 28, city: "New York");

EligibleForClub(name:) :-
  Person(name:, age:, city:),
  (age >= 25 && (city == "New York" || city == "San Francisco"));
```

Predicate `ClubEligibility` is computed with a single pass over `Person` predicate rows, while if
propositional disjunction was used it would be computed as union of two rules and would naively
result in two passes.

We can also logic of eligibility expressed with boolean connectives to an auxiliary predicate
and it will be injectible since it is a single conjunctive rule

```
IsEiligible(age, city) :-
  age >= 25 && (city == "New York" || city == "San Francisco");

EligibleForClub(name:) :-
  Person(name:, age:, city:), IsEligible(age, city);
```

## Recursion

Logica does allow recursion, for example given predicate `Parent` we can find acnestors
via rules:

```
Ancestor(x, y) :- Parent(x, y);
Ancestor(x, z) :- Parent(x, y), Ancestor(y, z);
```

Recursion is only allowed for concrete predicates in Logica. Recursive predicates are computed
via iteration, starting from an empty predicate and applying the rules a fixed number of steps,
which is 8 (eitght) by default. For example predicate `N` defined as

```
N(0);
N(n + 1) :- N(n);
```

evaluates to

```
+------+
| col0 |
+------+
|    8 |
|    7 |
|    6 |
|    5 |
|    4 |
|    3 |
|    2 |
|    1 |
|    0 |
+------+
```

You can change the number of recursion iterations with `@Recursive` annotation. So to make `N` contain all numbers
upto 20 one would need to define it as


```
@Recursive(N, 20);
N(0);
N(n + 1) :- N(n);
```

For iteration to kick-off predicate in DNF should have a disjunct that is not recursive. Which means it either needs to
be defined via multiple rules, at least one of which is non-recursive, or be defined via a disjunction, where at least
one disjunct is not recursive. For instance `Ancestor` can also be defined as:

```
Ancestor(x, z) distinct :- Parent(x, z) | Parent(x, y), Ancestor(y, z);
```

Aggregation is fine in recursive predictes. We just need to make sure that it is a well defined predicate, that is
signature of all rules is the same.
For example if `E(a, b)` is a predicate represending an
edge going from `a` to `b` in a directed graph, then we can find the length `D(x, y)` of the shortest path
between `x` and `y`, aka distance, as follows.

```
D(x, y) Min= 1 :- E(x, y);
D(x, z) Min= D(x, y) + D(y, z);
```

First rule states that if there is an edge from x to y then distance is 1 or less.
It will never be less, but we are using Min aggregation operator to be compatible with the second rule.
The second rule states that distance is subject to triangle inequality.


Using functional value for aggregation, like in the example above is often
helping readability. Of course, you are free to use aggregation of positional arguments as well.

Let us extend the example to also find the shortest path in the named argument `path`.
It is convenient to store the path excluding the final destination because in this case
paths before and after mid-point simply concatenate to the path from source to target. We leave it as a
simple exersice to the reader to write a post-processing predicate that holds the full path.

```
D(x, y, path? ArgMin= [x] -> 1) Min= 1 :- E(x, y);
D(x, z, path? ArgMin= ArrayConcat(path1, path2) -> d) Min= d :-
  d = D(x, y, path: path1) + D(y, z, path: path2);
```

First rule states that if there is an edge from `x` to `y` then you just go through `x` 
efore getting to your destination. Second rule states that if there is a path from `x` to `y`
and a path from `y` to `z` then path from `x` to `z` is concatenation of paths.

## Functors

Logica introduces _functors_ to re-use pieces of high level logica.

For example, let's say we implemented predicate `MostExpensiveTicket`, which finds
most expensive ticked in each purches of movie tickets recorded in table `Purchase`.


```
MostExpensiveTicket(purchase_id:, price:) :-
  Purchase(purchase_id:, tickets:),
  price = Max{ticket.price :- ticket in tickets};
```

What if we now want to apply the same logic of finding most expensive ticket to a table
`PurchaseZoo`? There is no way to pass the input data with the tools that we have learned.

Functor is a function from named tuples of predicates to predicates.
Functors are second order functions, which are functions from tuples of sets to sets. In Logica they map named tuples, as regular functions.

Any predicate defined in the program can act as a functor using any subset of predicates that are involved in its definition.

To create a predicate via functor call use syntax 

```
NewPredicate := FunctorPredicate(Arg1: Value1, Arg2: Value2, …);
```

Functor calls can only be made at the top level. You can not call functor in a body of a rule.

Functor call obtains new predicate by substituting predicates in the rules of the functor.
Functor application is similar to (class inference + methods override) in common imperative languages.

For example program

```
F(x) :- A(x) | B(x);
G := F(A: C, B: D);
```

results in `G` that acts as if defined as

```
G(x) :- C(x) | D(x);
```

With functors we can build `MostExpensiveZooTicket` from `MostExpensiveTicket` as follows.

```
MostExpensiveZooTicket := MostExpensiveTicket(Purchase: PurchaseZoo);
```
