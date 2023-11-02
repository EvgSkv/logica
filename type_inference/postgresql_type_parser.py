str_type = "Str"
num_type = "Num"
bool_type = "Bool"

unvariable_types_dict = {}
unvariable_types_dict["boolean"] = bool_type
unvariable_types_dict["bool"] = bool_type

unvariable_types_dict["bigint"] = num_type
unvariable_types_dict["int8"] = num_type
unvariable_types_dict["bigserial"] = num_type
unvariable_types_dict["serial8"] = num_type
unvariable_types_dict["double precision"] = num_type
unvariable_types_dict["float8"] = num_type
unvariable_types_dict["integer"] = num_type
unvariable_types_dict["int"] = num_type
unvariable_types_dict["int4"] = num_type
unvariable_types_dict["money"] = num_type
unvariable_types_dict["real"] = num_type
unvariable_types_dict["float4"] = num_type
unvariable_types_dict["smallint"] = num_type
unvariable_types_dict["int2"] = num_type
unvariable_types_dict["smallserial"] = num_type
unvariable_types_dict["serial2"] = num_type
unvariable_types_dict["serial"] = num_type
unvariable_types_dict["serial4"] = num_type

unvariable_types_dict["varbit"] = str_type
unvariable_types_dict["box"] = str_type
unvariable_types_dict["bytea"] = str_type
unvariable_types_dict["cidr"] = str_type
unvariable_types_dict["circle"] = str_type
unvariable_types_dict["date"] = str_type
unvariable_types_dict["inet"] = str_type
unvariable_types_dict["json"] = str_type
unvariable_types_dict["jsonb"] = str_type
unvariable_types_dict["line"] = str_type
unvariable_types_dict["lseg"] = str_type
unvariable_types_dict["macaddr"] = str_type
unvariable_types_dict["path"] = str_type
unvariable_types_dict["pg_lsn"] = str_type
unvariable_types_dict["point"] = str_type
unvariable_types_dict["polygon"] = str_type
unvariable_types_dict["text"] = str_type
unvariable_types_dict["timetz"] = str_type
unvariable_types_dict["timestamptz"] = str_type
unvariable_types_dict["tsquery"] = str_type
unvariable_types_dict["tsvector"] = str_type
unvariable_types_dict["txid_snapshot"] = str_type
unvariable_types_dict["uuid"] = str_type
unvariable_types_dict["xml"] = str_type


def __try_parse_variable_type(pg_type: str) -> str | None:
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


def try_parse_postgresql_type(pg_type: str) -> str | None:
    type_in_lowercase = pg_type.lower()
    if type_in_lowercase in unvariable_types_dict:
        return unvariable_types_dict[type_in_lowercase]
    else:
        return __try_parse_variable_type(type_in_lowercase)
