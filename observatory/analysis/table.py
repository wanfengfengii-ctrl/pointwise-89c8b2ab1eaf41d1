from dataclasses import dataclass
from fractions import Fraction
from observatory.intake.schema import normalize_schema
from observatory.intake.assignments import enumerate_assignments
from observatory.intake.frequencies import validate_frequencies, total_count


@dataclass(frozen=True)
class ProbabilityTable:
    schema: tuple
    masses: tuple

    @property
    def rows(self):
        return tuple(zip(enumerate_assignments(self.schema), self.masses))

    @property
    def mass(self):
        return sum(self.masses, Fraction())


def validate_table(table):
    schema = normalize_schema(table.schema)
    if schema != table.schema or not isinstance(table.masses, tuple):
        raise ValueError('table must have immutable canonical axes and cells')
    if len(table.masses) != len(enumerate_assignments(schema)):
        raise ValueError('table does not cover joint domain')
    if any(not isinstance(p, Fraction) or p < 0 for p in table.masses):
        raise ValueError('table masses must be nonnegative Fractions')
    return table


def table_from_frequencies(frequencies):
    table = validate_frequencies(frequencies.schema, frequencies.rows)
    total = total_count(table)
    return validate_table(ProbabilityTable(
        table.schema, tuple(Fraction(n, total) for n in table.counts)))
