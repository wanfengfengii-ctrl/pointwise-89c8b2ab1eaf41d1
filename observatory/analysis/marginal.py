from fractions import Fraction
from observatory.intake.assignments import enumerate_assignments
from observatory.analysis.table import ProbabilityTable, validate_table
from observatory.analysis.projection import axis_positions, project_assignment


def marginalize(table, names):
    validate_table(table)
    positions = axis_positions(table.schema, tuple(names))
    schema = tuple(table.schema[i] for i in positions)
    cells = dict.fromkeys(enumerate_assignments(schema), Fraction())
    for assignment, probability in table.rows:
        key = project_assignment(assignment, positions)
        cells[key] += probability
    return validate_table(ProbabilityTable(schema, tuple(cells.values())))
