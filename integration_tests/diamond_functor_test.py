"""Regression tests for copied recursive components and their private state.

Run: python3 integration_tests/diamond_functor_test.py
"""
import csv
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DiamondFunctorTest(unittest.TestCase):
  def run_program(self, source, mode, predicate='Test'):
    source = source.replace('MODE', mode)
    result = subprocess.run(
        [sys.executable, str(ROOT / 'logica.py'), '-', 'run_to_csv', predicate],
        input=source, capture_output=True, text=True, cwd=ROOT, timeout=30,
        env=dict(os.environ, LOGICA_PARSER='CPP'))
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    return sorted(tuple(row.values())
                  for row in csv.DictReader(io.StringIO(result.stdout)))

  def test_copied_closure_runs_more_than_one_round(self):
    source = '''
      @Engine("duckdb");
      @Recursive(Closure, DEPTH, mode: "MODE");
      Closure(a, b) distinct :- R(a, b);
      Closure(a, b) distinct :- Closure(a, x), Closure(x, b);
      Parent("A", "B"); Parent("B", "C"); Parent("C", "D");
      Test := Closure(R: Parent);
    '''
    expected = [('A', 'B'), ('A', 'C'), ('A', 'D'),
                ('B', 'C'), ('B', 'D'), ('C', 'D')]
    for mode in ('diamond', 'socratic'):
      for depth in ('8', '∞'):
        with self.subTest(mode=mode, depth=depth):
          self.assertEqual(self.run_program(source.replace('DEPTH', depth), mode),
                           expected)

  def test_original_and_two_copies_keep_separate_state(self):
    source = '''
      @Engine("duckdb");
      @Recursive(Closure, DEPTH, mode: "MODE");
      R("a", "b"); R("b", "c");
      S("x", "y"); S("y", "z");
      U("u", "v");
      Closure(a, b) distinct :- R(a, b);
      Closure(a, b) distinct :- Closure(a, x), Closure(x, b);
      Second := Closure(R: S);
      Third := Closure(R: U);
      Test("original", a, b) :- Closure(a, b);
      Test("second", a, b) :- Second(a, b);
      Test("third", a, b) :- Third(a, b);
    '''
    expected = [('original', 'a', 'b'), ('original', 'a', 'c'),
                ('original', 'b', 'c'), ('second', 'x', 'y'),
                ('second', 'x', 'z'), ('second', 'y', 'z'),
                ('third', 'u', 'v')]
    for mode in ('diamond', 'socratic'):
      for depth in ('8', '∞'):
        with self.subTest(mode=mode, depth=depth):
          self.assertEqual(self.run_program(source.replace('DEPTH', depth), mode),
                           expected)

  def test_coloring_verdicts_remain_independent_when_combined(self):
    source = (ROOT / 'integration_tests/socratic/psql_graph_coloring_test.l'
              ).read_text().replace('mode: "socratic"', 'mode: "MODE"')
    for mode in ('diamond', 'socratic'):
      with self.subTest(mode=mode):
        self.assertEqual(self.run_program(source, mode),
                         [('G1', 'colorable'), ('G2', 'not colorable')])

  def test_copied_stop_predicates_observe_only_their_own_state(self):
    source = '''
      @Engine("duckdb");
      Step() = 1; BigStep() = 2;
      @Recursive(N, ∞, mode: "MODE", stop: Stop);
      N() = 0 :- ~N();
      N() = N() + Step();
      Stop() :- N() > 5;
      M := N(Step: BigStep);
      Test("one", N()); Test("two", M());
    '''
    for mode in ('diamond', 'socratic'):
      with self.subTest(mode=mode):
        # Do not prescribe the stop/final-pass convention here: each
        # mode must give the same result alone and alongside its copy.
        n = self.run_program(source, mode, 'N')[0][0]
        m = self.run_program(source, mode, 'M')[0][0]
        self.assertEqual(self.run_program(source, mode),
                         [('one', n), ('two', m)])


if __name__ == '__main__':
  unittest.main()
