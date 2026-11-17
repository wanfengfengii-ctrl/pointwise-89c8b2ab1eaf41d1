"""Exact partial identification of conditional risk under a known channel.

The fixed revision supplies an observed joint probability ``p``.  The channel
``C`` is a nonnegative Fraction matrix whose rows follow the observed joint
domain and whose columns follow the latent joint domain; every column sums to
one.  The compatible true distributions are

    Q = {q : q >= 0, sum(q) = 1, C q = p}.

Because every channel column sums to one and ``p`` sums to one, ``sum(q) = 1``
follows from ``C q = p``.  ``Q`` is a bounded polyhedron, so it is nonempty
exactly when it has a vertex, and every vertex has linearly independent
support columns.  Vertices are recovered by exactly solving square
full-column-rank subsystems; domains hold at most eight joint cells, so full
vertex enumeration is intentional.  Linear-fractional extrema over ``Q`` with
a strictly positive denominator are attained at vertices.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations

from observatory.intake.schema import normalize_schema, schema_cardinality, valid_label
from observatory.intake.assignments import enumerate_assignments
from observatory.analysis.table import table_from_frequencies

CHANNEL_INTERPRETATION = 'channel_conditional_risk_range'
CHANNEL_STATUSES = ('incompatible', 'undefined_condition', 'bounded')
MAX_JOINT_CELLS = 8


@dataclass(frozen=True)
class ChannelQuery:
    latent_schema: tuple
    channel: tuple
    event: tuple
    condition: tuple

    def to_public_record(self):
        return {
            'latent_variables': [[v.name, list(v.domain)] for v in self.latent_schema],
            'channel': [[value for value in row] for row in self.channel],
            'event': dict(self.event),
            'condition': dict(self.condition),
        }


@dataclass(frozen=True)
class ChannelOutcome:
    status: str
    lower: object
    upper: object


def _as_sequence(value, message):
    if isinstance(value, (str, bytes)):
        raise ValueError(message)
    try:
        return tuple(value)
    except TypeError as exc:
        raise ValueError(message) from exc


def _check_cardinality(schema, label):
    cells = schema_cardinality(schema)
    if cells > MAX_JOINT_CELLS:
        raise ValueError(label + ' joint domain must have one to eight cells')
    return cells


def normalize_partial_assignment(schema, assignment):
    """Copy a partial latent assignment into canonical schema order."""
    if not isinstance(assignment, Mapping):
        raise ValueError('event and condition must be mappings')
    names = {v.name for v in schema}
    for key in assignment:
        if not isinstance(key, str) or key not in names:
            raise ValueError('unknown latent variable in event or condition')
    normalized = []
    for variable in schema:
        if variable.name in assignment:
            value = assignment[variable.name]
            if not valid_label(value) or value not in variable.domain:
                raise ValueError('event or condition outside latent domain: ' + variable.name)
            normalized.append((variable.name, value))
    return tuple(normalized)


def normalize_channel(observed_schema, latent_schema, channel):
    rows_expected = _check_cardinality(observed_schema, 'observed')
    columns_expected = _check_cardinality(latent_schema, 'latent')
    rows = _as_sequence(channel, 'channel must be an ordered sequence of rows')
    if len(rows) != rows_expected:
        raise ValueError('channel rows must match the observed joint domain')
    normalized = []
    for row in rows:
        values = _as_sequence(row, 'channel rows must be ordered sequences')
        if len(values) != columns_expected:
            raise ValueError('channel columns must match the latent joint domain')
        for value in values:
            if type(value) is not Fraction or value < 0:
                raise ValueError('channel cells must be nonnegative Fractions')
        normalized.append(values)
    for index in range(columns_expected):
        if sum((row[index] for row in normalized), Fraction()) != 1:
            raise ValueError('channel columns must sum exactly to one')
    return tuple(normalized)


def normalize_channel_query(observed_schema, latent_variables, channel, event, condition):
    observed_schema = normalize_schema(observed_schema)
    latent_schema = normalize_schema(latent_variables)
    normalized_channel = normalize_channel(observed_schema, latent_schema, channel)
    normalized_event = normalize_partial_assignment(latent_schema, event)
    normalized_condition = normalize_partial_assignment(latent_schema, condition)
    return ChannelQuery(latent_schema, normalized_channel,
                        normalized_event, normalized_condition)


def _mask(schema, assignments):
    positions = {variable.name: index for index, variable in enumerate(schema)}
    mask = []
    for cell in enumerate_assignments(schema):
        mask.append(all(cell[positions[name]] == value for name, value in assignments))
    return tuple(mask)


def _unique_solution(columns, target):
    """Solve the selected column subsystem exactly; None if no unique solution."""
    width = len(columns)
    height = len(target)
    rows = [[columns[j][i] for j in range(width)] + [target[i]]
            for i in range(height)]
    pivot_row = 0
    pivots = []
    for column in range(width):
        selected = None
        for row in range(pivot_row, height):
            if rows[row][column] != 0:
                selected = row
                break
        if selected is None:
            continue
        rows[pivot_row], rows[selected] = rows[selected], rows[pivot_row]
        divisor = rows[pivot_row][column]
        rows[pivot_row] = [value / divisor for value in rows[pivot_row]]
        for row in range(height):
            if row != pivot_row and rows[row][column] != 0:
                factor = rows[row][column]
                rows[row] = [left - factor * right
                             for left, right in zip(rows[row], rows[pivot_row])]
        pivots.append(column)
        pivot_row += 1
        if pivot_row == height:
            break
    for row in range(pivot_row, height):
        if all(rows[row][column] == 0 for column in range(width)) \
                and rows[row][width] != 0:
            return None
    if len(pivots) != width:
        return None
    solution = [Fraction()] * width
    for index, column in enumerate(pivots):
        solution[column] = rows[index][width]
    return solution


def enumerate_vertices(channel, target):
    """Return every vertex of {q >= 0 : channel q = target} exactly."""
    row_count = len(channel)
    column_count = len(channel[0]) if row_count else 0
    if row_count == 0 or column_count == 0:
        return ()
    columns = tuple(tuple(row[j] for row in channel) for j in range(column_count))
    found = {}
    for size in range(1, min(row_count, column_count) + 1):
        for selection in combinations(range(column_count), size):
            solution = _unique_solution(
                tuple(columns[j] for j in selection), target)
            if solution is None or any(value < 0 for value in solution):
                continue
            point = [Fraction()] * column_count
            for index, value in zip(selection, solution):
                point[index] = value
            found[tuple(point)] = None
    return tuple(found)


def run_channel_query(revision, query):
    normalized = normalize_channel_query(
        revision.schema, query.latent_schema, query.channel,
        dict(query.event), dict(query.condition))
    if normalized != query:
        raise ValueError('channel query is not canonical')
    latent_schema = normalized.latent_schema
    target = table_from_frequencies(revision.candidate.frequencies).masses
    vertices = enumerate_vertices(normalized.channel, target)
    if not vertices:
        return ChannelOutcome('incompatible', None, None)
    condition_mask = _mask(latent_schema, normalized.condition)
    event_mask = _mask(latent_schema, normalized.event)
    both_mask = tuple(left and right for left, right in zip(event_mask, condition_mask))
    masses = []
    for point in vertices:
        masses.append(sum((point[i] for i in range(len(point)) if condition_mask[i]),
                          Fraction()))
    if any(mass == 0 for mass in masses):
        return ChannelOutcome('undefined_condition', None, None)
    ratios = []
    for point, denominator in zip(vertices, masses):
        numerator = sum((point[i] for i in range(len(point)) if both_mask[i]),
                        Fraction())
        ratios.append(numerator / denominator)
    return ChannelOutcome('bounded', min(ratios), max(ratios))
