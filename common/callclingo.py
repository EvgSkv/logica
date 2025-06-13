#!/usr/bin/python
#
# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Provides integration with Clingo (Answer Set Programming) for Logica."""

import json

try:
    import clingo
except ImportError as e:
    raise ImportError(
        "The 'clingo' Python package is required for ClingoToLogica. "
        "Install it with: pip install clingo"
    ) from e

def _run_clingo(script: str):
    """Execute a Clingo script and return the answer sets using the Clingo Python API."""
    answer_sets = []

    class Collector:
        def __init__(self):
            self.models = []

        def on_model(self, model):
            atoms = [str(atom) for atom in model.symbols(shown=True)]
            self.models.append(atoms)

    collector = Collector()
    ctl = clingo.Control()
    ctl.configuration.solve.models = 0  # 0 means all possible answer sets
    try:
        ctl.add("base", [], script)
        ctl.ground([("base", [])])
        ctl.solve(on_model=collector.on_model)
    except Exception as e:
        raise RuntimeError(f"Clingo execution failed: {e}")

    # Convert answer sets to Logica-compatible format
    for atoms in collector.models:
        atom_strings = []
        for atom in atoms:
            atom_strings.append(str(atom))
        answer_sets.append(atom_strings)
    return answer_sets

def ClingoToLogica(script: str) -> str:
    """
    Execute a Clingo script and return results as a list of possible worlds,
    each with a world id and a list of predicate strings (e.g., 'attack(b,a)').
    """
    answer_sets = _run_clingo(script)
    result = []
    for idx, atom_strings in enumerate(answer_sets, start=1):
        result.append({"world_id": idx, "predicates": atom_strings})
    return json.dumps(result)

def ClingoToLogicaFile(script: str, filename: str):
    """
    Execute a Clingo script and write the possible worlds as JSON to a file.
    """
    answer_sets = _run_clingo(script)
    result = []
    for idx, answer_set in enumerate(answer_sets, start=1):
        predicates = []
        for pred_name, args in answer_set.items():
            if args:
                arg_strs = [str(arg) for arg in args]
                pred_str = f"{pred_name}({', '.join(arg_strs)})"
            else:
                pred_str = pred_name
            predicates.append(pred_str)
        result.append({"world_id": idx, "predicates": predicates})
    with open(filename, "w") as f:
        json.dump(result, f) 