# Test of using PostegreSQL structures.

@Engine("psql");

Word("fire");
Word("water");
Word("wind");
Word("sun");

WordAndLength({word:, length: Length(word)}) :-
  Word(word);

WordsByLengthList() Array= length -> {word:, length:} :-
  WordAndLength(word_and_length),
  word == word_and_length.word,
  length == word_and_length.length;

Test := WordsByLengthList()
# If test fails create the type by running:
# create type StringNumPair AS (first text, second numeric);

