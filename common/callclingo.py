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

def _import_clingo():
    try:
        import clingo
        return clingo
    except ImportError as e:
        raise ImportError(
            "The 'clingo' Python package is required for this function. "
            "Install it with: pip install clingo"
        ) from e

def RunClingo(script: str):
    """
    Execute a Clingo script and return results as a list of possible worlds,
    each with a world id and a list of predicate objects with predicate name and args.
    """
    clingo = _import_clingo()
    answer_sets = []
    ctl = clingo.Control()
    ctl.configuration.solve.models = 0  # 0 means all possible answer sets
    ctl.add("base", [], script)
    ctl.ground([("base", [])])
    with ctl.solve(yield_=True) as handle:
        for idx, model in enumerate(handle, start=1):
            predicates = []
            for atom in model.symbols(atoms=True):
                predicates.append({
                    "predicate": atom.name,
                    "args": [str(arg) for arg in atom.arguments]
                })
            answer_sets.append({"model_id": idx, "model": predicates})
    return json.dumps(answer_sets)

def RunClingoFile(script_file: str) -> str:
    """
    Execute a Clingo script from a file and return results as a JSON string.
    
    Args:
        script_file: Path to the file containing the Clingo program
    
    Returns:
        JSON string containing the answer sets
    """
    # Read the Clingo program from the file
    try:
        with open(script_file, 'r') as f:
            script = f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Clingo script file not found: {script_file}")
    except Exception as e:
        raise RuntimeError(f"Error reading Clingo script file: {e}")
    
    # Execute the script using RunClingo and return the result
    return RunClingo(script) 