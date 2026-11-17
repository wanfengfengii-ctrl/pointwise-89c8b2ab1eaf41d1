from observatory.intake.assignments import enumerate_assignments
from observatory.analysis.table import ProbabilityTable, validate_table


def axis_positions(schema, names):
    names = tuple(names)
    available = [v.name for v in schema]
    if any(not isinstance(name, str) for name in names):
        raise ValueError('axis names must be strings')
    if len(set(names)) != len(names) or any(name not in available for name in names):
        raise ValueError('unknown or duplicate axis')
    return tuple(available.index(name) for name in names)


def project_assignment(assignment, positions):
    return tuple(assignment[i] for i in positions)


def reorder_table(table, names):
    validate_table(table)
    names = tuple(names)
    positions = axis_positions(table.schema, names)
    if len(positions) != len(table.schema):
        raise ValueError('reorder must retain every axis')
    schema = tuple(table.schema[i] for i in positions)
    cells = {project_assignment(key, positions): value for key, value in table.rows}
    return validate_table(ProbabilityTable(
        schema, tuple(cells[key] for key in enumerate_assignments(schema))))
