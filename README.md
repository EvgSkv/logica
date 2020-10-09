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

Logica is an open source logic programming
language for data manipulation. Logica is a successor to
[Yedalog](https://research.google/pubs/pub43462/),
a language created at Google earlier.

### Why?

Logica is for engineers, data scientists and other specialists who want to use
logic programming syntax when writing queries and pipelines to run on
[BigQuery](https://cloud.google.com/bigquery).

Logica compiles to StandardSQL and gives you access to the power of BigQuery
engine with the convenience of logic programming syntax. This is useful because
BigQuery is magnitudes more powerful than state of the art native
logic programming engines.

We encourage you to try Logica, especially if

*   you already use logic programming and need more computational power, **or**
*   you use SQL, but feel unsatisfied about its readability, **or**
*   you want to learn logic programming and apply it to processing of Big Data.

In the future we plan to support more SQL dialects and engines.

### I have not heard of logic programming. What is it?

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

### How does Logica work?

Logica compiles the logic program into a SQL expression, so it can be executed
on BigQuery, the state of the art SQL engine.

Among database theoreticians Datalog and SQL are known to be _equivalent_. And
indeed the conversion from Datalog to SQL and back is often straightforward.
However there are a few nuances, for example how to treat disjunction and
negation. In Logica we tried to make choices that make understanding of the
resulting SQL structure as easy as possible, thus empowering user to write
programs that are executed efficiently.

### How to learn?

Learn basics of Logica by reading through tutorial located at `tutorial` folder.
See examples of using Logica in `examples` folder. Tutrial and examples show how
to access Logica from CoLab.

### Why is it called _Logica_?

_Logica_ stands for _**Logic** with **a**ggregation_.

### Installation

_To be written._

### Contact

_To be written._

---

Unless otherwise noted, the Logica source files are distributed
under the Apache 2.0 license found in the LICENSE file.

This is not an officially supported Google product.


