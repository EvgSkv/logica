#!/usr/bin/python
#
# Copyright 2024 Logica Authors
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

import os

if '.' not in __package__:
  from type_inference import type_retrieval_service_base
  from type_inference import psql_type_retrieval_service
  from type_inference import bq_type_retrieval_service
  from type_inference import unsupported_engine_exception
else:
  from ..type_inference import type_retrieval_service_base
  from ..type_inference import psql_type_retrieval_service
  from ..type_inference import bq_type_retrieval_service
  from ..type_inference import unsupported_engine_exception


def get_type_retrieval_service(engine: str, 
                               parsed_rules: dict, 
                               predicates_list: list) -> \
                        type_retrieval_service_base.TypeRetrievalServiceBase:
    running_from_colab = os.getenv('COLAB_RELEASE_TAG')
    if engine == 'psql':
      if running_from_colab:
        service = psql_type_retrieval_service.PostgresqlTypeRetrievalService(
        parsed_rules, predicates_list)
      else:
        connection_str = os.environ.get('LOGICA_PSQL_CONNECTION')
        service = psql_type_retrieval_service.PostgresqlTypeRetrievalService(
        parsed_rules, predicates_list, connection_str)
      return service
    elif engine == 'bigquery':
      from google import auth as terminal_auth
      credentials, project = terminal_auth.default()
      if not project:
        from google.colab import auth as colab_auth
        colab_auth.authenticate_user()
        print("Please enter project_id to use for BigQuery queries.")
        project = input()
        print("project_id is set to %s" % project)
      return bq_type_retrieval_service.BigQueryTypeRetrievalService(
        parsed_rules, predicates_list, credentials, project)
    else:
      raise unsupported_engine_exception.UnsupportedEngineException(engine)
