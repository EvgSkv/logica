# Logica Program Syntax

Here is a semi-formal [BNF](https://en.wikipedia.org/wiki/Backus%E2%80%93Naur_form) of Logica program.

```

// Program is a sequence of entries separated by semicolon.
program ::= program_entry (';' program_entry)* [;]

// Each entry is an import, a rule, or a functor application.
program_entry ::= import | rule | functor_application

// Example of an import -- import path.to.file.Predicate as AnotherPredicate
import ::=
  'import' dot_separated_path '.' logica_predicate ['as' logica_predicate]
dot_separated_path ::= [^<newline>]+

// Predicate defined by the program is alphanumeric starting with an
// uppercase letter.
logica_predicate  ::= [A-Z_][0-9a-zA-Z_]*

// You can also use database tables as predicates. 
predicate ::= logica_predicate | '`'[^`]+'`' | [A-Za-z_0-9.]+

// Variable must be lowercase numeric.
variable ::= [a-z0-9_]

// Rule is a head with an optional body.
rule ::= rule_head [ ':-' rule_body ]

// Body of the rule is a proposition.
rule_body ::= proposition

// Head of a rule is a call with an optional assignment and
// an optional 'distinct' denotation.
rule_head ::= head_call [assignment] ['distinct']

// Example of a simple assignment is -- = 2 * x
// and example of an aggregating assignment is -- List= 2 * x.
assignment ::= simple_assignment | aggregating_assignment
simple_assignment ::= '=' expression
aggregating_operator ::= ('+' | logica_predicate) '='
aggregating_assignment ::= aggregating_operator expression

// No space is allowed between predicate name and the opening
// parenthesis.
call ::= predicate '(' record_internal ')'
head_call ::= logica_predicate '(' aggregating_record_internal ')'

// Example of record_internal -- a: 5, b: 2 * x
record_field_value ::= field ':' expression
record_internal ::= 
  [record_field_value (',' record_field_value)* [',' '..' variable]] |
  ('..' variable)

// Example of aggregating_field_value -- x? += 5
aggregating_field_value ::= field '?' aggregating_assignment
aggregating_record_internal  ::=
  [record_field_value | aggregating_field_value]
  [',' (record_field_value | aggregating_field_value)]*

// Expression is a predicate call, operation, combine,
// list inclusion, implication or an object description.
expression ::=
  call |
  unary_operator_call |
  binary_operator_call |
  combine |
  inclusion |
  implication |
  string_literal |
  number_literal |
  boolean_literal |
  null_literal |
  list |
  record |
  ('(' expression ')')

operator ::= '+'|'-'|'/'|'>'|'<'|'<='|'>='|'=='|'->'|'&&'|'||'

unary_operator ::= '!'|'-'

unary_operator_call ::= unary_operator expression
binary_operator_call ::= expression operator expression

// Example of inclusion -- x in [1,2,3,4]
inclusion ::= expression 'in' expression

// Example of an implication -- if a == b then 7 else 9
implication ::=
  '(' 'if' expression then expression
  ['else if' expression 'then' expression]*
  'else' expression ')'

// If combine has a body then it must be enclosed in parenthesis.
combine ::= 'combine' aggregating_assignment [':-' rule_body]

// Concrete object specification.
string_literal ::= '"'[^"<newline>]'"'
number_literal ::= [0-9]+ [ '.'[0-9]+ ]
boolean_literal ::= 'true'|'false'
null_literal ::= 'null'
list ::= '[' [expression [','expression]*] ']'
record ::= '{' record_internal '}'

// Proposition is a conjunction, disjunction, negation,
// a predicate call, operation, or list inclusion.
proposition ::=
  conjunction |
  disjunction |
  negation |
  call |
  binary_operator_call |
  unary_operator_call |
  assign_combination |
  inclusion |
  ('(' proposition ')')

conjunction ::= proposition (',' proposition)*
disjunction ::= proposition ('|' proposition)*
negation ::= '~' proposition

// Example of assign combination -- l List= (2 * x :- x in [1,2,3])
assign_combination ::= variable
  aggregating_assignment |
  (aggregating_operator '(' expression ':-' proposition ')')

// Example of a functor application -- F := G(A: B)
functor_application ::= logica_predicate ':=' logica_predicate '(' functor_record_internal ')'
functor_record_internal ::=
  [logica_predicate ':' logica_predicate]
  (',' logica_predicate ':' logica_predicate )*


```

**Comments**: A symbol `#` occurring outside of a string starts a comment that
goes to the end of the line. A combination `/*` occurring anywhere outside a string
starts a comment that goes to the first occurence of `/*`.

