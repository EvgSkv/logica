from functools import cache
from typing import Dict
from type_inference.postgresql_type_parser import try_parse_postgresql_type
import psycopg2
from os import linesep

from type_inference.type_retrieval_exception import TypeRetrievalException

built_in_types = set()


def InitBuiltInTypes(connection_string: str):
    if built_in_types:
        return

    with psycopg2.connect(connection_string) as conn:
        with conn.cursor() as cur:
            # this SQL query returns all primitive types (defined by PostgreSQL directly)
            cur.execute('''
SELECT t.typname as type
FROM pg_type t
         LEFT JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
WHERE n.nspname = 'pg_catalog'
  AND (
            t.typrelid = 0 OR (SELECT c.relkind = 'c'
                               FROM pg_catalog.pg_class c
                               WHERE c.oid = t.typrelid)
    )
  AND NOT EXISTS(
        SELECT 1
        FROM pg_catalog.pg_type el
        WHERE el.oid = t.typelem
          AND el.typarray = t.oid
    );''')
            built_in_types.update((t[0] for t in cur.fetchall()))


@cache
def unpack_type(udt_type: str, conn) -> str:
    if udt_type in built_in_types:
        return try_parse_postgresql_type(udt_type)

    if udt_type.startswith('_'):
        return f'[{unpack_type(udt_type.lstrip("_"), conn)}]'

    with conn.cursor() as cur:
        # this SQL query returns all children (= fields) of given udt_type (named by parent_type) and its types
        cur.execute('''
SELECT pg_attribute.attname AS field_name,
    child_type.typname AS field_type
FROM pg_type AS parent_type
    JOIN pg_attribute ON pg_attribute.attrelid = parent_type.typrelid
    JOIN pg_type AS child_type ON child_type.oid = pg_attribute.atttypid
WHERE parent_type.typname = '{%s}';''', (udt_type,))

        fields = (f'{field_name}: {unpack_type(field_type, conn)}' for field_name, field_type in cur.fetchall())
        return f'{{{", ".join(fields)}}}'


def ValidateRuleAndGetTableName(rule: dict) -> str:
    rule_text = rule['full_text']
    field_value = rule['head']['record']['field_value']

    if len(field_value) != 1 or field_value[0]['field'] != '*':
        raise TypeRetrievalException(rule_text)

    conjuncts = rule['body']['conjunction']['conjunct']

    if len(conjuncts) != 1:
        raise TypeRetrievalException(rule_text)

    conjunct = conjuncts[0]

    if 'predicate' not in conjunct:
        raise TypeRetrievalException(rule_text)

    field_values = conjunct['predicate']['record']['field_value']

    if len(field_values) != 1 or field_values[0]['field'] != '*':
        raise TypeRetrievalException(rule_text)

    return conjuncts[0]['predicate']['predicate_name'].split('.')[1]


class TypeRetrievalService:
    def __init__(self, parsed_rules, predicate_names,
                 connection_string='dbname=logica user=logica password=logica host=127.0.0.1'):
        predicate_names_as_set = set(predicate_names)
        self.parsed_rules = [r for r in parsed_rules if r['head']['predicate_name'] in predicate_names_as_set]
        self.connection_string = connection_string
        self.table_names = self.ValidateParsedRulesAndGetTableNames()
        InitBuiltInTypes(self.connection_string)

    def ValidateParsedRulesAndGetTableNames(self) -> Dict[str, str]:
        return {rule['head']['predicate_name']: ValidateRuleAndGetTableName(rule) for rule in self.parsed_rules}

    def RetrieveTypes(self, filename='default.l'):
        filename = filename.replace('.l', '_schema.l')
        with psycopg2.connect(self.connection_string) as conn:
            with conn.cursor() as cursor:
                # for each given table this SQL query returns json object
                # where keys are names of columns in that table and values are corresponding types
                cursor.execute('''
SELECT table_name, jsonb_object_agg(column_name, udt_name)
FROM information_schema.columns
GROUP BY table_name
HAVING table_name IN %s;''', (self.table_names.values(),))
                columns = {table: columns for table, columns in cursor.fetchall()}

            result = []

            for rule in self.parsed_rules:
                result.append(f'{rule["full_text"]},')
                local = []

                for column, udt_type in sorted(columns[self.table_names[rule['head']['predicate_name']]].items(), key=lambda t: t[0]):
                    local.append(f'{column}: {unpack_type(udt_type, conn)}')

                var_name = rule['head']['record']['field_value'][0]['value']['expression']['variable']['var_name']
                result.append(f'{var_name} ~ {{{", ".join(local)}}};{linesep}')

            with open(filename, 'w') as writefile:
                writefile.writelines(linesep.join(result))
