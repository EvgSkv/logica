class TypeRetrievalException(BaseException):
    def __init__(self, predicate_text: str):
        super().__init__(f'''Bad predicate to build scheme for: '{predicate_text}'

Scheme can be built for predicates of the form:
'<PredicateName>(..<name of row>) :- <name table>(..<name of row>);'
''')
