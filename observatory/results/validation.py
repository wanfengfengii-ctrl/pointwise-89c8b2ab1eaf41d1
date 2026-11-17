from fractions import Fraction
from observatory.intake.assignments import enumerate_assignments, normalize_assignment
from observatory.analysis.projection import axis_positions
from observatory.analysis.query import OBSERVATIONAL_INTERPRETATION


def _validate_result(task, result):
    if result.spec != task.spec:
        raise ValueError('result does not match the fixed task specification')
    if result.interpretation != OBSERVATIONAL_INTERPRETATION:
        raise ValueError('incorrect interpretation')
    mass = result.condition_mass
    if not isinstance(mass, Fraction) or not 0 <= mass <= 1:
        raise ValueError('invalid condition mass')
    if result.status == 'zero_condition':
        if mass != 0 or result.rows is not None:
            raise ValueError('zero condition cannot have a probability table')
        return result
    if result.status != 'computable' or mass <= 0 or not isinstance(result.rows, tuple):
        raise ValueError('invalid computable result')
    positions = axis_positions(task.spec.schema, task.spec.query.outputs)
    schema = tuple(task.spec.schema[i] for i in positions)
    expected = enumerate_assignments(schema)
    if len(result.rows) != len(expected):
        raise ValueError('incomplete output table')
    total = Fraction()
    for (assignment, probability), key in zip(result.rows, expected):
        if not isinstance(assignment, tuple):
            raise ValueError('assignment must be immutable')
        if normalize_assignment(schema, assignment) != key:
            raise ValueError('output assignments are not in declared order')
        if not isinstance(probability, Fraction) or probability < 0:
            raise ValueError('invalid probability')
        total += probability
    if total != 1:
        raise ValueError('probabilities must sum exactly to one')
    return result


def validate_result(task, result):
    try:
        return _validate_result(task, result)
    except (TypeError, AttributeError, IndexError) as exc:
        raise ValueError('malformed result candidate') from exc
