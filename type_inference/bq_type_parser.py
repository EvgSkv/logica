#!/usr/bin/python
#
# Copyright 2023 Logica Authors
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

BIGQUERY_TYPE_TO_LOGICA_TYPE = {
  'BIGNUMERIC': 'Num',
  'BOOL': 'Bool',
  'BYTES': 'Str',
  'DATE': 'Str',
  'DATETIME': 'Str',
  'FLOAT64': 'Num',
  'GEOGRAPHY': 'Str',
  'INT64': 'Num',
  'INTERVAL': 'Str',
  'JSON': 'Str',
  'NUMERIC': 'Num',
  'STRING': 'Str',
  'TIME': 'Str',
  'TIMESTAMP': 'Str'
}

def BigQueryTypeToLogicaType(bq_type: str):
  """Parses bq atomic type into logica type, drops parameter if needed."""
  def TryParseParametrizedBigQueryTypeToLogicaType(bq_type: str):
    if bq_type.startswith('BIGNUMERIC'):
      return 'Num'
    elif bq_type.startswith('BYTES'):
      return 'Str'
    elif bq_type.startswith('NUMERIC'):
      return 'Num'
    elif bq_type.startswith('STRING'):
      return 'Str'
    return None

  return (TryParseParametrizedBigQueryTypeToLogicaType(bq_type) or 
          BIGQUERY_TYPE_TO_LOGICA_TYPE.get(bq_type))
