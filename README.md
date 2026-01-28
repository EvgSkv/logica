<!--
Copyright 2020 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

# Logica: language of Big Data

Logica is an open source declarative logic programming
language for data manipulation. Logica is a successor to
[Yedalog](https://research.google/pubs/pub43462/),
a language created at Google earlier.

## Why?

Logica is for engineers, data scientists and other specialists who want to use
logic programming syntax when writing queries and pipelines for databases and datawarehouses.
Logica programs run on
[BigQuery](https://cloud.google.com/bigquery), [Postgres](https://postgresql.org) and [SQLite](https://www.sqlite.org/).

Logica compiles to SQL and gives you access to the power of SQL ecosystem
with the convenience of logic programming syntax. 

This is useful because
SQL engines are magnitudes more powerful than state of the art native
logic programming engines. For example, BigQuery is a distributed datawarehouse and thus logic programs written
in Logica can be easily parallelized onto thousands of servers. Postgres and SQLite are among most popular databases, they are
capable of processing substantial volumes of data right on your machine.

We encourage you to try Logica, especially if

*   you already use logic programming and need more computational power, **or**
*   you already have data in BigQuery, PostgreSQL or SQLite, **or**
*   you want to learn logic programming and apply it to processing of Big Data.

Support for more SQL dialects and engines is coming in the future.

## I have not heard of logic programming. What is it?

Logic programming is a declarative programming paradigm where the program is
written as a set of logical statements.

Logic programming was developed in academia from the late 60s. Prolog and
Datalog are the most prominent examples of logic programming languages. Logica
is a language of the Datalog family.

Datalog and relational databases start from the same idea: think of data
as relations and think of data manipulation as a sequence of operations over
these relations. But Datalog and SQL differ in how these operations are
described. Datalog is inspired by the mathematical syntax of the first order
propositional logic and SQL follows the syntax of natural language.

SQL was based on the natural language to give access to databases to the people
without formal training in computer programming or mathematics. This convenience
may become costly when the logic that you want to express is non trivial.
There are many examples of hard-to-read SQL queries that correspond to simple
logic programs.

## How does Logica work?

Logica compiles the logic program into a SQL expression, so it can be executed
on BigQuery, the state of the art SQL engine.

Among database theoreticians Datalog and SQL are known to be _equivalent_. And
indeed the conversion from Datalog to SQL and back is often straightforward.
However there are a few nuances, for example how to treat disjunction and
negation. In Logica we tried to make choices that make understanding of the
resulting SQL structure as easy as possible, thus empowering user to write
programs that are executed efficiently.

## Why is it called _Logica_?

_Logica_ stands for _**Logic** with **a**ggregation_.

## How to learn?

Learn basics of Logica with the [CoLab tutorial](https://colab.research.google.com/github/EvgSkv/logica/blob/main/tutorial/Logica_DuckDB_tutorial.ipynb) located at [`tutorial`](https://github.com/EvgSkv/logica/tree/main/tutorial) folder.
See examples of using Logica in [`examples`](https://github.com/EvgSkv/logica/tree/main/examples) folder.

Tutorial and examples show how to access Logica from CoLab. You can also install Logica command line tool.

## Prerequisites

To run Logica programs on BigQuery you will need a 
[Google Cloud Project](https://console.cloud.google.com/projectcreate).
Once you have a project you can run Logica programs in CoLab providing your project id.

To run Logica locally you need [Python3](https://www.python.org/downloads/).

To initiate Logica predicates execution from the command line 
you will need `bq`, a
BigQuery [command line tool](https://cloud.google.com/bigquery/docs/bq-command-line-tool). For that you need to install 
[Google Cloud SDK](https://cloud.google.com/sdk/docs/install).

## Installation

Google Cloud Project is the only thing you need to run Logica in Colab, see
[Hello World example](https://colab.research.google.com/github/EvgSkv/logica/blob/main/examples/Logica_example_Hello_World.ipynb).

You can install Logica command with `pip` as follows.

```sh
# Install.
python3 -m pip install logica
# Run:
# To see usage message.
python3 -m logica
# To print SQL for HelloWorld program.
python3 -m logica - print Greet <<<'@Engine("sqlite"); Greet(greeting: "Hello world!")'
# To run HelloWorld program on SQLite.
python3 -m logica - run Greet <<<'@Engine("sqlite"); Greet(greeting: "Hello world!")'
```

If your `PATH` includes Python's `bin` folder then you will also be able to
run it simply as

```sh
logica - print Greet <<<'Greet(greeting: "Hello world!")'
```

Alternatively, you can clone GitHub repository:

```sh
git clone https://github.com/evgskv/logica
cd logica
./logica - print Greet <<<'Greet(greeting: "Hello world!")'
```


## Code samples

Here a couple examples of how Logica code looks like.

### Prime numbers

Find prime numbers less than 30 with SQLite.

Program `primes.l`:
```
# Using SQLite engine.
@Engine("sqlite");

# Define numbers 1 to 30.
Number(x + 1) :- x in Range(30);

# Defining composite numbers.
Composite(a * b) distinct :- Number(a), Number(b), a > 1, b > 1;

# Defining primes as "not composite".
Prime(n) distinct :- Number(n), n > 1, ~Composite(n);
```

Running `primes.l`
```sh
$ logica primes.l run Prime
+-------+
| prime |
+-------+
|     2 |
|     3 |
|     5 |
|     7 |
|    11 |
|    13 |
|    17 |
|    19 |
|    23 |
|    29 |
+-------+
```

### Cities with largest beer variety

Let's use beer variety dataset from [plotly](https://github.com/plotly/datasets/blob/master/beers.csv).

Let us find top 5 states with largest variety of beers. In each state we will pick city with the largest
variety in the state.

To run this example you will need to install DuckDB if you don't yet have it on your system. Luckily installing DuckDB is easy:

```
python3 -m pip install duckdb
```

Program `beer.l`:

```
@Engine("duckdb");

@Ground(Beer);
Beer(..r) :- 
    `('https://github.com/plotly/datasets/blob/master/beers.csv?raw=true')`(..r);

BeersInState(state) += 1 :- Beer(state:);
BeersInCity(state, city) += 1 :- Beer(state:, city:);

ArgMax5(x) = ArgMaxK(x, 5);
BestCityForBeer(state:, city:,
                city_beers: BeersInCity(state, city),
                state_beers: BeersInState(state)) :-
    state in ArgMax5{s -> BeersInState(s)},
    city = ArgMax{c -> BeersInCity(state, c)};
```

Running `beer.l`:

```
# logica beer.l run BestCityForBeer
+-------+--------------+------------+-------------+
| state | city         | city_beers | state_beers |
+-------+--------------+------------+-------------+
| IN    | Indianapolis | 43         | 139         |
| CO    | Boulder      | 41         | 265         |
| CA    | San Diego    | 42         | 183         |
| TX    | Austin       | 25         | 130         |
| MI    | Grand Rapids | 66         | 162         |
+-------+--------------+------------+-------------+
```

<!--
### News mentions

Who was mentioned in the news in 2020 the most?
Let's query [GDELT Project](https://www.gdeltproject.org/) dataset.

Program `mentions.l`
```
@OrderBy(Mentions, "mentions desc");
@Limit(Mentions, 10);
Mentions(person:, mentions? += 1) distinct :-
  gdelt-bq.gdeltv2.gkg(persons:, date:),
  Substr(ToString(date), 0, 4) == "2020",
  the_persons == Split(persons, ";"),
  person in the_persons;
```

Running `mentions.l`
```
$ logica mentions.l run Mentions
+----------------+----------+
|     person     | mentions |
+----------------+----------+
| donald trump   |  3624228 |
| joe biden      |  1591320 |
| los angeles    |  1221998 |
| george floyd   |   923472 |
| boris johnson  |   845955 |
| barack obama   |   541672 |
| vladimir putin |   486428 |
| bernie sanders |   409224 |
| andrew cuomo   |   375594 |
| nancy pelosi   |   375373 |
+----------------+----------+
```

Note that cities of Los Angeles and Las Vegas are mentioned in this table due to known
missclasification issue in the GDELT data analysis.
--> 

## Citations
For citations, see our list of [Logica publications](https://logica-lang.github.io/publications/).

## Feedback

Feel free to create [github issues](https://github.com/EvgSkv/logica/issues)
for bugs and feature requests.

You questions and comments are welcome at our [github discussions](https://github.com/EvgSkv/logica/discussions)!



---

Unless otherwise noted, the Logica source files are distributed
under the Apache 2.0 license found in the LICENSE file.

This is not an officially supported Google product.


