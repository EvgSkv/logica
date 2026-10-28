"""Regression tests for functional inputs and custom Socrates aggregates.

Run: python3 integration_tests/socratic/functional_inputs_test.py
"""
import collections
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from compiler import dialects, neural_logica
from parser_py import parse


class FunctionalInputsTest(unittest.TestCase):
  def rules(self, text):
    rules_of = collections.defaultdict(list)
    text += '\n' + dialects.Get('duckdb').LibraryProgram()
    for rule in parse.ParseFile(text)['rule']:
      rules_of[rule['head']['predicate_name']].append(rule)
    return rules_of

  def test_nested_scalar_helpers(self):
    rules = self.rules('''
      Shortest(p) = ArgMin(p -> Size(p));
      Wrapped(p) = Shortest(p);
      s(x) = ToString(x);
      Format(x) = s(x);
    ''')
    for name in ('Shortest', 'Wrapped', 's', 'Format'):
      with self.subTest(name=name):
        self.assertTrue(neural_logica.IsFunctional(name, rules))

  def test_bound_helper_inputs_remain_groundable(self):
    rules = self.rules('''
      s(x) = ToString(x);
      Format(x) = s(x);
      Domain(1); Domain(2);
      Table(x) = Format(x) :- Domain(x);
      Generated(x) = Format(x) :- x in Range(3);
      Total() = Sum{x :- Domain(x)};
    ''')
    for name in ('Table', 'Generated', 'Total'):
      with self.subTest(name=name):
        self.assertFalse(neural_logica.IsFunctional(name, rules))

  def test_recursive_relations_terminate_analysis(self):
    rules = self.rules('''
      A(x) = B(x);
      B(x) = A(x);
      B(0) = 1;
    ''')
    self.assertFalse(neural_logica.IsFunctional('A', rules))
    self.assertFalse(neural_logica.IsFunctional('B', rules))

  def test_functional_dependency_propagates_around_cycle(self):
    rules = self.rules('''
      A(x) = B(x);
      B(x) = A(x);
      B(x) = ToString(x);
    ''')
    self.assertTrue(neural_logica.IsFunctional('A', rules))
    self.assertTrue(neural_logica.IsFunctional('B', rules))

  def run_predicate(self, source, predicate, text=None):
    result = subprocess.run(
        [sys.executable, str(ROOT / 'logica.py'), str(source),
         'run_to_csv', predicate], input=text, capture_output=True, text=True,
        cwd=ROOT, timeout=120,
        env=dict(os.environ, LOGICA_PARSER=os.environ.get('LOGICA_PARSER', 'CPP')))
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    return list(csv.DictReader(io.StringIO(result.stdout)))

  def test_shortest_paths_against_breadth_first_search(self):
    source = Path(__file__).with_name('custom_shortest_path.l')
    edges = {(int(r['col0']), int(r['col1']))
             for r in self.run_predicate(source, 'G')}
    neighbors = collections.defaultdict(set)
    for a, b in edges:
      neighbors[a].add(b)
    expected = {}
    for start in neighbors:
      # Paths in the rule contain at least one edge, including cycles.
      queue = collections.deque((v, 1) for v in neighbors[start])
      seen = set()
      while queue:
        end, distance = queue.popleft()
        if end in seen:
          continue
        seen.add(end)
        expected[start, end] = distance
        queue.extend((v, distance + 1) for v in neighbors.get(end, ()))
    actual = {}
    for row in self.run_predicate(source, 'Path'):
      start, end = int(row['col0']), int(row['col1'])
      path = json.loads(row['logica_value'])
      self.assertTrue(path)
      self.assertEqual(path[0], start)
      for edge in zip(path, path[1:] + [end]):
        self.assertIn(edge, edges)
      self.assertNotIn((start, end), actual)
      actual[start, end] = len(path)
    self.assertEqual(actual, expected)

  def test_custom_min_preserves_argument_transform(self):
    rows = self.run_predicate('-', 'Score', '''
      @Engine("duckdb", threads: 2);
      AbsMin(x) = Min(Abs(x));
      @Recursive(Score, 2, mode: "socratic");
      Score() AbsMin= -2;
      Score() AbsMin= 3;
      Score() AbsMin= Score();
    ''')
    self.assertEqual(len(rows), 1)
    self.assertEqual(float(rows[0]['logica_value']), 2)

  def test_longest_common_subsequence_with_string_concatenation(self):
    source = '''
      @Engine("duckdb");
      Word1(i) = Substr(s, i + 1, 1) :-
        s = WORD1, i in Range(Length(s));
      Word2(i) = Substr(s, i + 1, 1) :-
        s = WORD2, i in Range(Length(s));
      @Recursive(CommonLongest, mode: "socratic");
      CommonLongest(i + 1, j + 1) ArgMax= Word1(i) -> 1 :-
        Word1(i) == Word2(j);
      CommonLongest(i + 1, j) ArgMax= s -> Length(s) :-
        s = CommonLongest(i, j), Word1(i);
      CommonLongest(i, j + 1) ArgMax= s -> Length(s) :-
        s = CommonLongest(i, j), Word2(j);
      CommonLongest(i + 1, j + 1) ArgMax=
          seq ++ Word1(i) -> (Length(seq) + 1) :-
        CommonLongest(i, j) = seq, Word1(i) = Word2(j);
    '''

    def is_subsequence(sequence, word):
      remaining = iter(word)
      return all(any(c == x for x in remaining) for c in sequence)

    for a, b in [('HIEROGLYPHOLOGY', 'MICHELANGELO'),
                 ('ABABA', 'BAAAB'), ('КОШКА', 'КРОШКА')]:
      with self.subTest(words=(a, b)):
        program = source.replace('WORD1', json.dumps(a, ensure_ascii=False))
        program = program.replace('WORD2', json.dumps(b, ensure_ascii=False))
        rows = self.run_predicate('-', 'CommonLongest', program)
        lengths = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
        for i, x in enumerate(a):
          for j, y in enumerate(b):
            lengths[i + 1][j + 1] = (
                lengths[i][j] + 1 if x == y else
                max(lengths[i][j + 1], lengths[i + 1][j]))
        expected = {(i, j): lengths[i][j]
                    for i in range(1, len(a) + 1)
                    for j in range(1, len(b) + 1) if lengths[i][j]}
        actual = {}
        for row in rows:
          i, j = int(row['col0']), int(row['col1'])
          sequence = row['logica_value']
          self.assertNotIn((i, j), actual)
          self.assertTrue(is_subsequence(sequence, a[:i]))
          self.assertTrue(is_subsequence(sequence, b[:j]))
          actual[i, j] = len(sequence)
        # Check every prefix pair, without prescribing the tie-breaking
        # choice among equally long valid subsequences.
        self.assertEqual(actual, expected)


if __name__ == '__main__':
  unittest.main()
