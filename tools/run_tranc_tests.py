#!/usr/bin/env python3
"""Run tranc tests. Each .py file runs on Python and on tranc -r, outputs must match."""

import subprocess
import sys
import os

TESTS = [
  "basics",
  "loops",
  "functions",
  "nested",
  "ifelse",
  "classes",
  "strings",
  "lists",
  "dicts",
  "mixed",
  "comprehensions",
  "print_containers",
  "sets",
  "isinstance_test",
  "none_assert",
  "csv_graph",
]

TRANC = os.path.join(os.path.dirname(__file__), "tranc.py")
TEST_DIR = os.path.join(os.path.dirname(__file__), "tranc_tests")


RUN_DIR = os.path.dirname(__file__)

def run(cmd, timeout=30):
  r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                     cwd=RUN_DIR)
  return r.returncode, r.stdout, r.stderr


def main():
  passed = 0
  failed = 0
  errors = []

  for test in TESTS:
    path = os.path.join(TEST_DIR, test + ".py")
    label = test

    # Run with Python.
    py_rc, py_out, py_err = run(["python3", path])
    if py_rc != 0:
      print(f"  SKIP  {label} (python failed: {py_err.strip()})")
      continue

    # Run with tranc.
    tr_rc, tr_out, tr_err = run(["python3", TRANC, path, "-r"])

    if tr_rc != 0:
      print(f"  FAIL  {label} (tranc error)")
      errors.append((label, "tranc failed:\n" + tr_err))
      failed += 1
      continue

    if py_out == tr_out:
      print(f"  OK    {label}")
      passed += 1
    else:
      print(f"  FAIL  {label} (output mismatch)")
      errors.append((label,
        f"python:\n{py_out}\ntranc:\n{tr_out}"))
      failed += 1

  print(f"\n{passed} passed, {failed} failed, {len(TESTS)} total")

  if errors:
    print("\n--- Failures ---")
    for label, detail in errors:
      print(f"\n[{label}]")
      print(detail)

  sys.exit(1 if failed else 0)


if __name__ == "__main__":
  main()
