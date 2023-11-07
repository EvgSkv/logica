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

str_type = "Str"
num_type = "Num"
bool_type = "Bool"

POSTGRES_TYPE_TO_LOGICA_TYPE = {
  "boolean": bool_type,
  "bool": bool_type,
  "bigint": num_type,
  "int8": num_type,
  "bigserial": num_type,
  "serial8": num_type,
  "double precision": num_type,
  "float8": num_type,
  "integer": num_type,
  "int": num_type,
  "int4": num_type,
  "money": num_type,
  "real": num_type,
  "float4": num_type,
  "smallint": num_type,
  "int2": num_type,
  "smallserial": num_type,
  "serial2": num_type,
  "serial": num_type,
  "serial4": num_type,
  "varbit": str_type,
  "box": str_type,
  "bytea": str_type,
  "cidr": str_type,
  "circle": str_type,
  "date": str_type,
  "inet": str_type,
  "json": str_type,
  "jsonb": str_type,
  "line": str_type,
  "lseg": str_type,
  "macaddr": str_type,
  "path": str_type,
  "pg_lsn": str_type,
  "point": str_type,
  "polygon": str_type,
  "text": str_type,
  "timetz": str_type,
  "timestamptz": str_type,
  "tsquery": str_type,
  "tsvector": str_type,
  "txid_snapshot": str_type,
  "uuid": str_type,
  "xml": str_type
}


def TryParsePostgresTypeToLogicaType(pg_type: str) -> str | None:
  if pg_type.startswith("bit"):
    return str_type
  elif pg_type.startswith("char"):
    return str_type
  elif pg_type.startswith("varchar"):
    return str_type
  elif pg_type.startswith("interval"):
    return str_type
  elif pg_type.startswith("numeric"):
    return num_type
  elif pg_type.startswith("decimal"):
    return num_type
  elif pg_type.startswith("time"):
    return str_type
  return None


def PostgresTypeToLogicaType(pg_type: str) -> str | None:
  type_in_lowercase = pg_type.lower()
  if type_in_lowercase in POSTGRES_TYPE_TO_LOGICA_TYPE:
    return POSTGRES_TYPE_TO_LOGICA_TYPE[type_in_lowercase]
  else:
    return TryParsePostgresTypeToLogicaType(type_in_lowercase)
