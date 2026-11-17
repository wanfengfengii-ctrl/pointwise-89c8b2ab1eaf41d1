from dataclasses import dataclass
from observatory.intake.schema import normalize_schema
from observatory.intake.frequencies import validate_frequencies, total_count


@dataclass(frozen=True)
class CandidateDistribution:
    frequencies: object

    @property
    def schema(self):
        return self.frequencies.schema

    @property
    def total(self):
        return total_count(self.frequencies)


def prepare_distribution(variables, rows):
    schema = normalize_schema(variables)
    return CandidateDistribution(validate_frequencies(schema, rows))
