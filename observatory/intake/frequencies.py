from dataclasses import dataclass
from observatory.intake.schema import normalize_schema
from observatory.intake.assignments import enumerate_assignments, normalize_assignment


@dataclass(frozen=True)
class FrequencyTable:
    schema: tuple
    counts: tuple

    @property
    def rows(self):
        return tuple(zip(enumerate_assignments(self.schema), self.counts))


def validate_frequencies(schema, rows):
    schema = normalize_schema(schema)
    expected = enumerate_assignments(schema)
    found = {}
    try:
        for assignment, count in rows:
            key = normalize_assignment(schema, assignment)
            if key in found:
                raise ValueError('duplicate assignment')
            if type(count) is not int or count < 0:
                raise ValueError('count must be a nonnegative integer')
            found[key] = count
    except TypeError as exc:
        raise ValueError('invalid frequency rows') from exc
    if set(found) != set(expected):
        raise ValueError('frequency rows must cover the full joint domain')
    table = FrequencyTable(schema, tuple(found[key] for key in expected))
    if total_count(table) <= 0:
        raise ValueError('total count must be positive')
    return table


def total_count(table):
    return sum(table.counts)
