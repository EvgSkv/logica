import csv

sources = []
targets = []
with open("tranc_tests/graph.csv") as f:
  reader = csv.reader(f)
  for row in reader:
    sources.append(int(row[0]))
    targets.append(int(row[1]))

nodes = set()
i = 0
while i < len(sources):
  nodes.add(sources[i])
  nodes.add(targets[i])
  i = i + 1

print(len(sources))
print(len(nodes))
print(sorted(nodes))
