#!/usr/bin/python
#
# Copyright 2020 Google LLC
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

"""Library for using Logica in CoLab."""

from common import color

from compiler import rule_translate
from compiler import universe

import IPython

from IPython.core.magic import register_cell_magic
from IPython.display import display

from parser_py import parse

from google.cloud import bigquery
from google.colab import widgets


PROJECT = None


def SetProject(project):
  global PROJECT
  PROJECT = project


@register_cell_magic
def logica(line, cell):
  Logica(line, cell, run_query=True)


def ParseList(line):
  line = line.strip()
  if not line:
    predicates = []
  else:
    predicates = [p.strip() for p in line.split(',')]
  return predicates


def RunSQL(sql, engine):
  if engine != 'bigquery':
    raise Exception('Logica colab only supports BigQuery for now.')
  client = bigquery.Client(project=PROJECT)
  return client.query(sql).to_dataframe()


def Logica(line, cell, run_query):
  """Running Logica predicates and storing results."""
  predicates = ParseList(line)
  try:
    parsed_rules = parse.ParseFile(cell)['rule']
  except parse.ParsingException as e:
    e.ShowMessage()
    return
  program = universe.LogicaProgram(parsed_rules)
  engine = program.annotations.Engine()

  bar = widgets.TabBar(predicates + ['(Log)'])
  logs_idx = len(predicates)

  ip = IPython.get_ipython()
  for idx, predicate in enumerate(predicates):
    with bar.output_to(logs_idx):
      print('Running %s' % predicate)
      try:
        sql = program.FormattedPredicateSql(predicate)
        ip.push({predicate + '_sql': sql})
      except rule_translate.RuleCompileException as e:
        e.ShowMessage()
        return

    # Publish output to Colab cell.
    with bar.output_to(idx):
      sub_bar = widgets.TabBar(['SQL', 'Result'])
      with sub_bar.output_to(0):
        print(
            color.Format(
                'The following query is stored at {warning}%s{end} '
                'variable.' % (
                    predicate + '_sql')))
        print(sql)

    with bar.output_to(logs_idx):
      if run_query:
        t = RunSQL(sql, engine)
        ip.push({predicate: t})

    with bar.output_to(idx):
      with sub_bar.output_to(1):
        if run_query:
          print(
              color.Format(
                  'The following table is stored at {warning}%s{end} '
                  'variable.' %
                  predicate))
          display(t)
        else:
          print('The query was not run.')
