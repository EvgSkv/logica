from functools import cache
from typing import Dict
import psycopg2

from type_inference.type_retrieval_exception import TypeRetrievalException


built_in_types = set()


def InitBuiltInTypes(connection_string: str):
    if built_in_types:
        return

    with psycopg2.connect(connection_string) as conn:
        with conn.cursor() as cur:
            cur.execute(f'''
SELECT t.typname as type
FROM pg_type t
    LEFT JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
WHERE (
        t.typrelid = 0 OR (
            SELECT c.relkind = 'c'
            FROM pg_catalog.pg_class c
            WHERE c.oid = t.typrelid
        )
    )
    AND NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_type el
        WHERE el.oid = t.typelem
            AND el.typarray = t.oid
    )
    AND n.nspname = 'pg_catalog';''')
            built_in_types.update([x[0] for x in cur.fetchall()])

@cache
def unpack_type(udt_type: str, conn) -> str:
    if udt_type in built_in_types:
        return udt_type

    if udt_type.startswith('_'):
        return f'[{unpack_type(udt_type.lstrip("_"), conn)}]'

    with conn.cursor() as cur:
        cur.execute(f'''
SELECT pg_attribute.attname AS field_name,
    child_type.typname AS field_type
FROM pg_type AS parent_type
    JOIN pg_attribute ON pg_attribute.attrelid = parent_type.typrelid
    JOIN pg_type AS child_type ON child_type.oid = pg_attribute.atttypid
WHERE parent_type.typname = '{udt_type}';''')

        type_info = []

        for field_name, field_type in cur.fetchall():
            type_info.append(f'{field_name}: {unpack_type(field_type, conn)}')

        return f'{{{", ".join(type_info)}}}'


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
    def __init__(self, parsed_rules, predicate_names, connection_string='dbname=logica user=logica password=logica host=127.0.0.1'):
        predicate_names_as_set = set(predicate_names)
        self.parsed_rules = [r for r in parsed_rules if r['head']['predicate_name'] in predicate_names_as_set]
        self.connection_string = connection_string
        self.table_names = self.ValidateParsedRulesAndGetTableNames()
        InitBuiltInTypes(self.connection_string)

    def ValidateParsedRulesAndGetTableNames(self) -> Dict[str, str]:
        mapping = dict()

        for rule in self.parsed_rules:
            mapping[rule['head']['predicate_name']] = ValidateRuleAndGetTableName(rule)

        return mapping

    def RetrieveTypes(self):
        with psycopg2.connect(self.connection_string) as conn: 
            joined_table_names = ','.join((f"'{n}'" for n in self.table_names.values()))

            with conn.cursor() as cursor:
                cursor.execute(f'''
SELECT table_name, jsonb_object_agg(column_name, udt_name)
FROM information_schema.columns
GROUP BY table_name
HAVING table_name IN ({joined_table_names});''')
                columns = {table: columns for table, columns in cursor.fetchall()}

            for rule in self.parsed_rules:
                print(rule['full_text'])
                
                for column, udt_type in columns[self.table_names[rule['head']['predicate_name']]].items():
                    print(column, ':', unpack_type(udt_type, conn))

                print()
