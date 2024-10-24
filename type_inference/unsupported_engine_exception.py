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

from logging import error

if '.' not in __package__:
  from common import color
  from type_inference import type_retrieval_exception
else:
  from ..common import color
  from ..type_inference import type_retrieval_exception


class UnsupportedEngineException(type_retrieval_exception.TypeRetrievalException):
  def __init__(self, engine: str):
    error(f'''{color.Format("[ {error}Error{end} ]")} Unsupported engine to build schema for: '{engine}'.
          Currently supported engines: psql, bigquery.
          ''')
