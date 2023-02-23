from parser_py import parse
import sys


def get_predicates(rule: dict) -> set:
    conjuncts = []
    if 'body' in rule:
        body_conjuncts = rule['body']['conjunction']['conjunct']
        conjuncts.extend(body_conjuncts)
    if 'record' in rule['head']:
        head_conjuncts = rule['head']['record']['field_value']
        conjuncts.extend(head_conjuncts)

    predicates = set()
    for conjunct in conjuncts:
        fill_predicates_list(conjunct, predicates)

    return predicates


def fill_predicates_list(dictionary: dict, predicates: set):
    try:
        for key, value in dictionary.items():
            if key == 'predicate_name':
                predicates.add(value)
            else:
                fill_predicates_list(value, predicates)
    except AttributeError:
        return


def connect_to_database():
    from sqlalchemy import create_engine
    return create_engine('postgresql+psycopg2://logica:logica@127.0.0.1', pool_recycle=3600)


def inspect_table(name: str, engine) -> list:
    from sqlalchemy import inspect
    inspector = inspect(engine)
    if not inspector.has_table(name):
        print(f"No such table {name}")
    else:
        return inspector.get_columns(name)


def run(raw_program: str):
    parsed = parse.ParseFile(raw_program)
    rules = parsed['rule']
    defined_predicates_names = set([rule['head']['predicate_name'] for rule in rules])
    all_predicates = set()
    for rule in rules:
        all_predicates = all_predicates.union(get_predicates(rule))
    unknown_predicates = all_predicates.difference(defined_predicates_names)

    engine = connect_to_database()
    for predicate in unknown_predicates:
        print(inspect_table(predicate, engine))

# Examples:
# Q(x, y, a) :- a == U(x), y == 1; A();
# Q(x, y) :- U(x), y == 1; A();
# StudentName(name:) :- students(name:);
# StudentName(name:) :- unknown_students(name:);
# Q(x: U(1), y: A()); A();
# Q(x: U(1), y: G()) :- V();
# Q(x: U(1));

# Run
# python3 -m type_inference.db_inspector 'StudentName(name:) :- students(name:);'


if __name__ == '__main__':
    run(sys.argv[1])
