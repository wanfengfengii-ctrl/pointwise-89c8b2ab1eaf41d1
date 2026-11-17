from dataclasses import dataclass
from fractions import Fraction
from collections.abc import Mapping
from observatory.intake.assignments import normalize_assignment
from observatory.analysis.table import ProbabilityTable, validate_table
from observatory.analysis.projection import axis_positions
from observatory.analysis.marginal import marginalize


@dataclass(frozen=True)
class ConditionalOutcome:
    status: str
    condition_mass: Fraction
    table: object


def condition_table(table, outputs, conditions):
    validate_table(table)
    outputs = tuple(outputs)
    if not isinstance(conditions, Mapping):
        raise ValueError('conditions must be a mapping')
    condition_names = tuple(conditions)
    positions = axis_positions(table.schema, condition_names)
    axis_positions(table.schema, outputs)
    if set(outputs) & set(condition_names):
        raise ValueError('output and condition axes overlap')
    condition_schema = tuple(table.schema[i] for i in positions)
    values = normalize_assignment(condition_schema, conditions)
    masses = tuple(
        probability if tuple(key[i] for i in positions) == values else Fraction()
        for key, probability in table.rows
    )
    selected = ProbabilityTable(table.schema, masses)
    denominator = selected.mass
    if denominator == 0:
        return ConditionalOutcome('zero_condition', Fraction(), None)
    marginal = marginalize(selected, outputs)
    normalized = ProbabilityTable(
        marginal.schema, tuple(p / denominator for p in marginal.masses))
    return ConditionalOutcome('computable', denominator, validate_table(normalized))
