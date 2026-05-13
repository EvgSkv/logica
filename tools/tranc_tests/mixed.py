def count_words(words: "std::vector<std::string>") -> "std::map<std::string, int64_t>":
  counts = {}
  for w in words:
    if w in counts:
      counts[w] = counts[w] + 1
    else:
      counts[w] = 1
  return counts

result = count_words(["a", "b", "a", "c", "b", "a"])
for k, v in result.items():
  print(k, v)
