#!/usr/bin/env python3

import os
import sys

# Ensure the repo root is importable when running as `python tools/...`.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
  sys.path.insert(0, _REPO_ROOT)

from parser_py import parse
from type_inference.research import infer


def main(argv: list[str]) -> int:
  demo_path = (
      argv[1]
      if len(argv) > 1
      else 'type_inference/research/integration_tests/typing_heritage_error_demo.l'
  )

  # Force the C++ parser path so this demo validates the C++->Python bridge.
  os.environ['LOGICA_PARSER'] = 'CPP'

  program_text = open(demo_path, 'r', encoding='utf-8').read()
  parsed_rules = parse.ParseFile(program_text)['rule']

  engine = infer.TypesInferenceEngine(parsed_rules, dialect='psql')
  engine.InferTypes()

  # Raises TypeErrorCaughtException with a message that includes
  # `expression_heritage.Display()`. This relies on correct heritage propagation.
  infer.TypeErrorChecker(parsed_rules).CheckForError(mode='raise')

  return 0


if __name__ == '__main__':
  raise SystemExit(main(sys.argv))
