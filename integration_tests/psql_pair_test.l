# Test of using PostegreSQL structures.

@Engine("psql");

Word("fire");
Word("water");
Word("wind");
Word("sun");

# We assume there exists StringNumPair
# (first text, second numeric) type.
StringNumPair(s, i) = SqlExpr("({s}, {i})::StringNumPair", {s:, i:});

WordAndLength(StringNumPair(word, Length(word))) :-
  Word(word);

WordsByLengthList() Array= length -> StringNumPair(word, length) :-
  WordAndLength(word_and_length),
  word == word_and_length.first,
  length == word_and_length.second;

Test := WordsByLengthList()

