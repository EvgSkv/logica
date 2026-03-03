@Engine("psql");

# This program is intentionally ill-typed.
# It triggers a type inference error that calls `expression_heritage.Display()`.
# If `expression_heritage` is not a HeritageAwareString (or span alignment is wrong),
# the resulting error loses context or crashes.
Demo(x: 1) :-
  # Include a non-ASCII character before the error site, to exercise
  # UTF-8 byte→char span decoding.
  y == "π",
  # Builtin Length expects positional argument 0, not a named field `str:`.
  Length(str: "abc");
