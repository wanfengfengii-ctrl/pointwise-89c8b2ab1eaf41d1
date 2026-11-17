from dataclasses import dataclass
from collections.abc import Mapping
from observatory.intake.assignments import normalize_assignment
from observatory.analysis.projection import axis_positions
from observatory.analysis.table import table_from_frequencies
from observatory.analysis.conditional import condition_table

OBSERVATIONAL_INTERPRETATION = 'observational_conditional_probability'


@dataclass(frozen=True)
class ObservationalQuery:
    outputs: tuple
    conditions: tuple

    def to_public_record(self):
        return {'outputs': list(self.outputs), 'conditions': dict(self.conditions)}


def validate_query(schema, outputs, conditions):
    if isinstance(outputs, (str, bytes)) or not isinstance(conditions, Mapping):
        raise ValueError('outputs must be a sequence and conditions a mapping')
    try:
        outputs = tuple(outputs)
    except TypeError as exc:
        raise ValueError('invalid outputs') from exc
    axis_positions(schema, outputs)
    axis_positions(schema, tuple(conditions))
    if set(outputs) & set(conditions):
        raise ValueError('output and condition axes overlap')
    selected = tuple(v for v in schema if v.name in conditions)
    values = normalize_assignment(selected, conditions)
    canonical = tuple((v.name, value) for v, value in zip(selected, values))
    return ObservationalQuery(outputs, canonical)


def run_query(revision, query):
    normalized = validate_query(revision.schema, query.outputs, dict(query.conditions))
    if normalized != query:
        raise ValueError('query is not canonical')
    return condition_table(table_from_frequencies(revision.candidate.frequencies),
                           query.outputs, dict(query.conditions))
