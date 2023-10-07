import psycopg2

conn = psycopg2.connect("dbname=logica user=logica password=logica host=127.0.0.1")
cur = conn.cursor()
cur.execute(f'''SELECT column_name, data_type, udt_name
               FROM information_schema.columns
               WHERE table_name = \'students\'''')
columns_with_types = cur.fetchall()

dict = {}

for column_with_type in columns_with_types:
    t = column_with_type[2].lstrip('_')
    cur.execute(f'''SELECT
      pg_attribute.attname AS field_name,
      t_0_pg_type.typname AS field_type
    FROM
      pg_type, pg_attribute, pg_type AS t_0_pg_type
    WHERE
      (pg_type.typname = \'{t}\') AND
      (pg_attribute.attrelid = pg_type.typrelid) AND
      (t_0_pg_type.oid = pg_attribute.atttypid)''')
    result = cur.fetchall()
    if not result:
        result = t
    if column_with_type[1] == 'ARRAY':
        result = [result]
    dict[column_with_type[0]] = result
    print(result)
print(dict)
cur.close()
conn.close()

