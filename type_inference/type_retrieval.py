import psycopg2
from column import Column


types_dict = {}
dict = {}

def unpack_type(column: Column):
    inner_type = column.udt_name.lstrip('_')
    cur.execute(f'''SELECT
          pg_attribute.attname AS field_name,
          t_0_pg_type.typname AS field_type
        FROM
          pg_type, pg_attribute, pg_type AS t_0_pg_type
        WHERE
          (pg_type.typname = \'{inner_type}\') AND
          (pg_attribute.attrelid = pg_type.typrelid) AND
          (t_0_pg_type.oid = pg_attribute.atttypid)''')
    type_info = cur.fetchall()
    if not type_info:
        type_info = inner_type
        if column.data_type == 'ARRAY':
            type_info = [type_info]
        dict[column.column_name] = type_info
        return
    types_dict[inner_type] = type_info
    if column.data_type == 'ARRAY':
        type_info = [type_info]
    dict[column.column_name] = type_info


conn = psycopg2.connect("dbname=logica user=logica password=logica host=127.0.0.1")
cur = conn.cursor()
cur.execute(f'''SELECT column_name, data_type, udt_name
               FROM information_schema.columns
               WHERE table_name = \'students\'''')
columns = [Column(*col) for col in cur.fetchall()]

for column in columns:
    unpack_type(column)
print(dict)
print(types_dict)
cur.close()
conn.close()

