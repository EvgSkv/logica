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

# Keeping the placeholder, but we may never needed.
# DuckDB is too easy to connect!

import json

if '.' not in __package__:
  from compiler.dialect_libraries import duckdb_library
  from common import clingo_logica
else:
  from ..compiler.dialect_libraries import duckdb_library
  from ..common import clingo_logica


display_style = ';'.join([
      'border: 1px solid rgba(0, 0, 0, 0.3)',
      'width: fit-content;',
      'padding: 20px',
      'border-radius: 5px',
      'min-width: 50em',
      'background-color: rgb(230, 240, 230)',
      'box-shadow: 1px 1px 3px rgba(0, 0, 0, 0.2)'])

display_id_counter = 0


def GetConnection(logica_program=None):
  import duckdb
  connection = duckdb.connect()
  if logica_program:
    a = logica_program.annotations.annotations
    clingo_settings = a.get('@Engine', {}).get('duckdb', {}).get('clingo', False)
    if clingo_settings or clingo_settings == {}:
      if clingo_settings == True:
        clingo_settings = {}
      default_opt_mode = clingo_settings.get('opt_mode', 'opt')
      ConnectClingo(connection,
                    default_opt_mode=default_opt_mode,
                    clingo_settings=clingo_settings,
                    logical_context=logica_program.raw_rules,
                    logica_program=logica_program)
  return connection


def ConnectClingo(connection,
                  display_code=False,
                  default_num_models=0,
                  default_opt_mode=None,
                  logical_context=None,
                  logica_program=None,
                  clingo_settings=None,
                  debug_printing=False):
  import clingo
  import duckdb
  from IPython.display import HTML
  from IPython.display import display
  from IPython.display import update_display

  model_type = duckdb.list_type(duckdb.row_type(
    fields={'predicate': str, 'args': duckdb.list_type(str)}))
  list_of_models_type = duckdb.list_type(
      duckdb.row_type(fields={'model': model_type,
                              'model_id': int}))
  substitutions_type = duckdb.list_type(
      duckdb.row_type(fields={'arg': str,
                              'value': str}))

  def RunClingo(program: str) -> list_of_models_type:
    # Создаем контроллер и загружаем программу.
    ctl = clingo.Control()
    ctl.add("base", [], program)
    ctl.configuration.solve.models = default_num_models
    if default_opt_mode:
      ctl.configuration.solve.opt_mode = default_opt_mode

    # Просим Clingo "заземлить" правила (подготовить к решению).
    ctl.ground([("base", [])])

    # Решаем и выводим результат.
    result = []
    with ctl.solve(yield_=True) as handle:
      for model_id, model in enumerate(handle):
        entry = []
        for s in model.symbols(atoms=True):
          entry.append({'predicate': s.name,
                        'args': list(map(str, s.arguments))})
        # For debugging.
        # print('?>', model.cost, model.optimality_proven)

        result.append({'model': entry, 'model_id': model_id})
      if handle.get().exhausted:  # All solutions found
        pass
        # For debugging.
        # print("Search exhausted - optimality should be proven")
    return result

  try:
      connection.remove_function('RunClingo')
  except:
      pass
  connection.create_function('RunClingo', RunClingo)

  def RunClingoFile(program_file: str) -> duckdb.list_type(
      duckdb.row_type(fields={'model': model_type,
                              'model_id': int})):
    program = open(program_file).read()
    return RunClingo(program)

  try:
      connection.remove_function('RunClingoFile')
  except:
      pass
  connection.create_function('RunClingoFile', RunClingoFile)

  def RunClingoTemplate(
        program_template: str,
        substitutions: substitutions_type) -> list_of_models_type:
    global display_id_counter
    # Start with the original template
    program = program_template

    # Apply each substitution
    for sub in substitutions:
      arg = sub['arg']
      value = sub['value']
      # Replace {arg} with value
      program = program.replace(f"{{{arg}}}", value)
    if display_code:
      display(HTML('<div style="%s"><pre>%s</pre></div>' % (
                       display_style, program)),
                   display_id='clingo_display_%d' % display_id_counter)
      display_id_counter += 1
    # Now run the substituted program
    return RunClingo(program)

  try:
      connection.remove_function('RunClingoTemplate')
  except:
      pass
  connection.create_function('RunClingoTemplate', RunClingoTemplate)

  def RunClingoFileTemplate(
      program_file: str,
      substitutions: substitutions_type) -> list_of_models_type:
    # Read the template file
    program_template = open(program_file).read()
    # Apply substitutions and run
    return RunClingoTemplate(program_template, substitutions)

  try:
      connection.remove_function('RunClingoFileTemplate')
  except:
      pass
  connection.create_function('RunClingoFileTemplate', RunClingoFileTemplate)

  def Clingo(predicates: duckdb.list_type(str),
             within_model: model_type) -> list_of_models_type:
    if logica_program:
      for p in predicates:
        if p not in logica_program.functors.args_of:
          continue
        for a in logica_program.functors.args_of[p]:
          if a in clingo_logica.SUPPORTED_PREDICATES:
            continue
          if a not in predicates:
            import sys
            hl = lambda x: '\033[1m%s\033[0m' % x
            print('Running Clingo for predicates: %s' % hl(','.join(predicates)))
            print('[ \033[91m Missing predicate \033[0m ] '
                  f'Predicate {hl(p)} depends on {hl(a)} but {hl(a)} was '
                  'not requested.')
            print('Request predicate even if its provided via facts.')
            print('This is required to avoid debugging caused by forgotten ')
            print('predicates.')
            assert False, 'Your happiness is my priority.'
    context = '\n'.join(clingo_logica.RenderKlingonModel(
        within_model, from_logica=True))
    program = clingo_logica.Klingon(logical_context, predicates)
    full_program = context + '\n' + program
    if debug_printing:
      print('=== Running Clingo ===')
      print('Predicates:', predicates)
      print('Within model:', within_model)
      print('Full Clingo Program:\n', full_program)
    return clingo_logica.RunClingo(full_program, clingo_settings)

  try:
      connection.remove_function('Clingo')
  except:
      pass
  connection.create_function('Clingo', Clingo)