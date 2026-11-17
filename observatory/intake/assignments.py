from collections.abc import Mapping
from itertools import product
from observatory.intake.schema import normalize_schema, valid_label


def normalize_assignment(schema, assignment):
    schema = normalize_schema(schema)
    if isinstance(assignment, Mapping):
        if set(assignment) != {v.name for v in schema}:
            raise ValueError('assignment must specify exactly the declared variables')
        values = tuple(assignment[v.name] for v in schema)
    else:
        if isinstance(assignment, (str, bytes)):
            raise ValueError('assignment must be a mapping or sequence')
        try:
            values = tuple(assignment)
        except TypeError as exc:
            raise ValueError('invalid assignment') from exc
    if len(values) != len(schema):
        raise ValueError('wrong assignment width')
    for variable, value in zip(schema, values):
        if not valid_label(value) or value not in variable.domain:
            raise ValueError('assignment outside domain: ' + variable.name)
    return values


def enumerate_assignments(schema):
    return tuple(product(*(v.domain for v in normalize_schema(schema))))


def assignment_position(schema, assignment):
    schema = normalize_schema(schema)
    values = normalize_assignment(schema, assignment)
    position = 0
    for variable, value in zip(schema, values):
        position = position * len(variable.domain) + variable.domain.index(value)
    return position
