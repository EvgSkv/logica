import psycopg2
from column import Column

built_in = {'int4', 'varchar', 'text'}

def unpack_type(udt_type: str) -> str:
    if udt_type in built_in:
        return udt_type
    if udt_type.startswith('_'):
        return f'[{unpack_type(udt_type.lstrip("_"))}]'
    cur.execute(f'''SELECT
          pg_attribute.attname AS field_name,
          t_0_pg_type.typname AS field_type
        FROM
          pg_type, pg_attribute, pg_type AS t_0_pg_type
        WHERE
          (pg_type.typname = \'{udt_type}\') AND
          (pg_attribute.attrelid = pg_type.typrelid) AND
          (t_0_pg_type.oid = pg_attribute.atttypid)''')
    type_info = []
    for field_name, field_type in cur.fetchall():
        type_info.append(f'{field_name}: {unpack_type(field_type)}')
    return f'{{{", ".join(type_info)}}}'


conn = psycopg2.connect("dbname=logica user=logica password=logica host=127.0.0.1")
cur = conn.cursor()
cur.execute(f'''SELECT column_name, data_type, udt_name
               FROM information_schema.columns
               WHERE table_name = \'students\'''')
columns = [Column(*col) for col in cur.fetchall()]

for column in columns:
    print(column.column_name, unpack_type(column.udt_name))
