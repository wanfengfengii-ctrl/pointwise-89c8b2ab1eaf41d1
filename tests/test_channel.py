"""Independent checks for channel partial identification.

The reference solver enumerates basic solutions from the row form
``C q = p`` together with the active nonnegativity rows, which is a different
construction from the production column-subset solver in
``observatory.analysis.channel``.  Only small rational domains are used.
"""
from dataclasses import replace
from fractions import Fraction
from itertools import combinations, product
from math import prod
from random import Random

from test_distribution import LabCase, make_lab
from observatory.tasks.repository import TaskRepository, TaskConflict
from observatory.tasks.serialization import encode_task_spec, decode_task_spec
from observatory.tasks.specification import ChannelTaskSpec
from observatory.tasks.execution import TaskExecutor
from observatory.results.serialization import encode_result, decode_result
from observatory.results.reading import ResultUnavailable
from observatory.results.export import export_result
from observatory.results.validation import validate_result
import json

LATENT = [["G", [0, 1]], ["Y", [0, 1]]]


def solve_square(rows, width):
    matrix = [list(row) for row in rows]
    for column in range(width):
        choice = None
        for row in range(column, width):
            if matrix[row][column] != 0:
                choice = row
                break
        if choice is None:
            return None
        matrix[column], matrix[choice] = matrix[choice], matrix[column]
        pivot = matrix[column][column]
        matrix[column] = [Fraction(value) / pivot for value in matrix[column]]
        for row in range(width):
            if row != column and matrix[row][column] != 0:
                factor = matrix[row][column]
                matrix[row] = [left - factor * right
                               for left, right in zip(matrix[row], matrix[column])]
    return [matrix[row][width] for row in range(width)]


def brute_vertices(channel, target):
    columns = len(channel[0])
    equalities = [list(row) + [value] for row, value in zip(channel, target)]
    planes = [[Fraction(int(j == k)) for j in range(columns)] + [Fraction()]
              for k in range(columns)]
    points = set()
    for chosen in combinations(range(len(equalities) + len(planes)), columns):
        rows = (equalities + planes)
        solution = solve_square([rows[index] for index in chosen], columns)
        if solution is None or any(value < 0 for value in solution):
            continue
        if sum(solution) != 1:
            continue
        if all(sum(row[j] * solution[j] for j in range(columns)) == value
               for row, value in zip(channel, target)):
            points.add(tuple(solution))
    return points


def mask(schema, partial):
    names = [name for name, domain in schema]
    keys = list(product(*(domain for name, domain in schema)))
    return tuple(all(key[names.index(name)] == value
                     for name, value in partial.items()) for key in keys)


def reference(schema, channel, target, event, condition):
    points = brute_vertices(channel, target)
    if not points:
        return 'incompatible', None, None
    event_mask = mask(schema, event)
    condition_mask = mask(schema, condition)
    masses = [{i: point[i] for i in range(len(point)) if condition_mask[i]}
              for point in points]
    if any(sum(m.values(), Fraction()) == 0 for m in masses):
        return 'undefined_condition', None, None
    ratios = []
    for point in points:
        denominator = sum((point[i] for i in range(len(point))
                           if condition_mask[i]), Fraction())
        numerator = sum((point[i] for i in range(len(point))
                         if event_mask[i] and condition_mask[i]), Fraction())
        ratios.append(numerator / denominator)
    return 'bounded', min(ratios), max(ratios)


class TestChannelReference(LabCase):
    counter = 0

    def save_channel(self, task_id, counts, latent, channel, event, condition,
                     dataset=None, source='channel'):
        variables = [["O", list(range(len(counts)))]]
        dataset = dataset or task_id
        revision = self.distributions.put_distribution(
            dataset, source, variables, [((i,), n) for i, n in enumerate(counts)])
        exact = [[Fraction(cell) for cell in row] for row in channel]
        self.tasks.save_channel_query(task_id, dataset, revision, latent, exact,
                                      event, condition)
        return revision

    def channel_result(self, task_id):
        return self.executor.execute_task(task_id)

    def check(self, counts, latent, channel, event, condition):
        TestChannelReference.counter += 1
        task_id = 'probe-' + str(TestChannelReference.counter)
        self.save_channel(task_id, counts, latent, channel, event, condition)
        result = self.channel_result(task_id)
        observed = [Fraction(n, sum(counts)) for n in counts]
        expected = reference(latent, [[Fraction(x) for x in row] for row in channel],
                             observed, event, condition)
        self.assertEqual((result.status, result.lower, result.upper), expected)
        self.assertEqual(result.interpretation, 'channel_conditional_risk_range')
        self.assertTrue(isinstance(result.spec, ChannelTaskSpec))
        return result, expected

    def test_hand_cases(self):
        cases = [
            ([3, 2, 0], LATENT,
             [[1, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]],
             {"Y": 1}, {"G": 1}, ('bounded', Fraction(0), Fraction(3, 5))),
            ([1, 1], LATENT, [[1, 1, 0, 0], [0, 0, 1, 1]],
             {"Y": 1}, {"G": 1}, ('bounded', Fraction(0), Fraction(1))),
            ([1, 1, 2, 4], LATENT,
             [[int(i == j) for j in range(4)] for i in range(4)],
             {"Y": 1}, {"G": 1}, ('bounded', Fraction(2, 3), Fraction(2, 3))),
            ([1, 1], [["Y", [0, 1]]], [[1, 1], [0, 0]],
             {"Y": 1}, {"Y": 1}, ('incompatible', None, None)),
            ([1], [["Y", [0, 1]]], [[1, 1]],
             {"Y": 1}, {"Y": 1}, ('undefined_condition', None, None)),
            ([10 ** 30, 1], [["Y", [0, 1]]], [[1, 0], [0, 1]],
             {"Y": 1}, {"Y": 1}, ('bounded', Fraction(1), Fraction(1))),
            ([1, 1], [["Y", [0, 1]]], [[1, 0], [0, 1]],
             {"Y": 0}, {"Y": 1}, ('bounded', Fraction(0), Fraction(0))),
            ([1], [], [[1]], {}, {}, ('bounded', Fraction(1), Fraction(1))),
        ]
        for index, (counts, latent, channel, event, condition, expected) in enumerate(cases):
            with self.subTest(index=index):
                task_id = 'hand-' + str(index)
                self.save_channel(task_id, counts, latent, channel, event, condition)
                result = self.channel_result(task_id)
                self.assertEqual((result.status, result.lower, result.upper), expected)
                if expected[0] == 'bounded':
                    self.assertIs(type(result.lower), Fraction)
                    self.assertIs(type(result.upper), Fraction)

    def test_redundant_channel_and_partial_overlap(self):
        result, expected = self.check(
            [1, 1, 2], [["Y", [0, 1]]],
            [[Fraction(1, 2), 0], [Fraction(1, 2), 0], [0, 1]],
            {"Y": 1}, {})
        self.assertEqual(expected, ('bounded', Fraction(1, 2), Fraction(1, 2)))
        # Event and condition overlap only at Y=1; empty mappings mean everything.
        result, expected = self.check(
            [1, 1, 2], [["Y", [0, 1]]],
            [[Fraction(1, 2), 0], [Fraction(1, 2), 0], [0, 1]],
            {}, {"Y": 1})
        self.assertEqual(expected, ('bounded', Fraction(1), Fraction(1)))

    def test_random_channels_against_reference(self):
        rng = Random(20261117)
        for trial in range(60):
            # Latent joint domain: one or two variables, at most eight cells.
            shapes = [[rng.choice([1, 2, 3, 4])], [rng.choice([2, 3]), 2],
                      [2, 2], [rng.choice([2, 3, 4])]]
            latent = []
            for index, size in enumerate(shapes[rng.randrange(len(shapes))]):
                latent.append((chr(ord('L') + index), list(range(size))))
            latent_units = prod(len(domain) for name, domain in latent)
            observed_cells = rng.choice([1, 2, 3, 4])
            channel = [[Fraction(rng.randrange(5)) for _ in range(latent_units)]
                       for _ in range(observed_cells)]
            for column in range(latent_units):
                total = sum(row[column] for row in channel)
                if total == 0:
                    channel[0][column] += Fraction(1)
                    total = 1
                for row in range(observed_cells):
                    channel[row][column] /= total
            if rng.random() < 0.2:
                counts = [rng.randrange(4) for _ in range(observed_cells)]
                counts[0] += 1
            else:
                hidden = [Fraction(rng.randrange(4)) for _ in range(latent_units)]
                total = sum(hidden)
                if total == 0:
                    hidden[0] = 1
                    total = 1
                hidden = [value / total for value in hidden]
                observed = [sum((channel[row][j] * hidden[j]
                                 for j in range(latent_units)), Fraction())
                            for row in range(observed_cells)]
                counts = [1] * observed_cells
            assignment = {}
            condition = {}
            for name, domain in latent:
                if rng.random() < 0.5:
                    assignment[name] = rng.choice(domain)
                if rng.random() < 0.5:
                    condition[name] = rng.choice(domain)
            task_id = 'random-' + str(trial)
            self.save_channel(task_id, counts, latent, channel,
                              assignment, condition, source=task_id)
            result = self.channel_result(task_id)
            observed = [Fraction(n, sum(counts)) for n in counts]
            expected = reference(latent, channel, observed, assignment, condition)
            self.assertEqual((result.status, result.lower, result.upper), expected,
                             (trial, counts, channel, assignment, condition))
            self.assertIn(result.status,
                          ('incompatible', 'undefined_condition', 'bounded'))
            if result.status == 'bounded':
                self.assertTrue(0 <= result.lower <= result.upper <= 1)

    def test_scale_and_input_rejection(self):
        revision = self.distributions.put_distribution(
            'big', 'scale', [['O', list(range(9))]], [((i,), 1) for i in range(9)])
        before = self.database.connection.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
        for latent, channel, event, condition in [
            ([["L", [0, 1]]], [[1, 0]] * 9, {}, {}),                # observed too wide
            ([["L", list(range(9))]], [[Fraction(1, 9)] * 9], {}, {}),  # latent too wide
            ([["L", [0, 1]]], [[1, 0]] * 8, {}, {}),                # row count mismatch
            ([["L", [0, 1]]], [[Fraction(1, 2), Fraction(1, 2)]] * 8, {}, {}),  # column sums
            ([["L", [0, 1]]], [[1, 0]] * 8 + [[1, 1]], {}, {}),
            ([["L", [0, 1]]], [[1.0, 0]] * 8, {}, {}),              # float
            ([["L", [0, 1]]], [[1, 0]] * 8, {'bad': 0}, {}),        # unknown latent
            ([["L", [0, 1]]], [[1, 0]] * 8, {}, {'L': 2}),          # outside domain
        ]:
            with self.subTest(channel=channel, event=event), self.assertRaises(ValueError):
                self.tasks.save_channel_query('invalid-scale', 'big', revision,
                                              latent, channel, event, condition)
        self.assertEqual(self.database.connection.execute(
            'SELECT COUNT(*) FROM tasks').fetchone()[0], before)

    def test_task_identity_conflict_and_cross_kind(self):
        revision = self.save_channel('identity', [3, 2, 0], LATENT,
                                     [[1, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]],
                                     {"Y": 1}, {"G": 1})
        again = self.tasks.save_channel_query(
            'identity', 'identity', revision, LATENT,
            [[Fraction(1), Fraction(0), Fraction(0), Fraction(1)],
             [Fraction(0), Fraction(0), Fraction(1), Fraction(0)],
             [Fraction(0), Fraction(1), Fraction(0), Fraction(0)]],
            {"Y": 1}, {"G": 1})
        self.assertEqual(again.spec, self.tasks.load('identity').spec)
        with self.assertRaises(TaskConflict):
            self.tasks.save_channel_query('identity', 'identity', revision, LATENT,
                                          [[Fraction(1), Fraction(0), Fraction(0), Fraction(1)],
                                           [Fraction(0), Fraction(0), Fraction(1), Fraction(0)],
                                           [Fraction(0), Fraction(1), Fraction(0), Fraction(0)]],
                                          {"G": 1, "Y": 1}, {"G": 0})
        with self.assertRaises(TaskConflict):
            self.tasks.save_channel_query('identity', 'identity', revision, LATENT,
                                          [[Fraction(0), Fraction(0), Fraction(0), Fraction(1)],
                                           [Fraction(1), Fraction(0), Fraction(1), Fraction(0)],
                                           [Fraction(0), Fraction(1), Fraction(0), Fraction(0)]],
                                          {"Y": 1}, {"G": 1})
        with self.assertRaises(TaskConflict):
            self.tasks.save_query('identity', 'identity', revision, ['O'], {})
        self.save_channel('observational', [3, 2, 0], LATENT,
                          [[1, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]], {"Y": 1}, {"G": 1})
        with self.assertRaises(TaskConflict):
            self.tasks.save_query('observational', 'observational', revision, ['O'], {})

    def test_guards_and_codec(self):
        revision = self.save_channel('guarded', [3, 2, 0], LATENT,
                                     [[1, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]],
                                     {"Y": 1}, {"G": 1})
        result = self.channel_result('guarded')
        task = self.tasks.load('guarded')
        self.assertEqual(decode_result(encode_result(result)), result)
        self.assertEqual(decode_task_spec(encode_task_spec(task.spec)), task.spec)
        good = result
        bad = [
            replace(good, spec=self.tasks.load('guarded').spec, lower=None),
            replace(good, lower=Fraction(0), upper=None),
            replace(good, lower=0.0),
            replace(good, lower=Fraction(-1)),
            replace(good, upper=Fraction(2)),
            replace(good, lower=Fraction(3, 5), upper=Fraction(1, 2)),
            replace(good, status='computable'),
            replace(good, status='incompatible'),
            replace(good, status='incompatible', lower=Fraction(0), upper=Fraction(1)),
            replace(good, interpretation='observational_conditional_probability'),
        ]
        other_revision = self.distributions.put_distribution(
            'other', 'guarded-other', [['O', [0, 1, 2]]],
            [((0,), 1), ((1,), 1), ((2,), 1)])
        self.tasks.save_channel_query('other', 'other', other_revision, LATENT,
                                      [[Fraction(x) for x in row] for row in
                                       [[1, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]]],
                                      {"Y": 1}, {"G": 1})
        bad.append(replace(good, spec=self.tasks.load('other').spec))
        for candidate in bad:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                validate_result(task, candidate)
            with self.assertRaises(ValueError):
                self.publisher.publish('guarded', candidate)
            self.assertEqual(self.tasks.load('guarded').state, 'completed')

    def test_persistence_correction_and_no_recompute(self):
        revision = self.save_channel('fixed', [3, 2, 0], LATENT,
                                     [[1, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]],
                                     {"Y": 1}, {"G": 1})
        original = self.channel_result('fixed')
        exported = self.reader.read_result('fixed', structured=True)
        self.assertEqual(exported['lower'], [0, 1])
        self.assertEqual(exported['upper'], [3, 5])
        self.assertEqual(json.loads(export_result(original)), exported)
        # Corrections create a new revision; the old binding stays fixed.
        self.distributions.put_distribution(
            'fixed', 'corrected', [['O', [0, 1, 2]]],
            [((0,), 1), ((1,), 4), ((2,), 0)])
        self.tasks.save_channel_query('new', 'fixed',
                                      self.distributions.current_revision('fixed'),
                                      LATENT, [[Fraction(x) for x in row] for row in
                                               [[1, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]]],
                                      {"Y": 1}, {"G": 1})
        new = self.channel_result('new')
        self.assertEqual((new.lower, new.upper), (Fraction(0), Fraction(1, 5)))
        self.assertEqual(original.spec.revision, revision)
        self.reopen()

        class NoChannelCompute(TaskExecutor):
            def _compute_channel(self, revision, query):
                raise AssertionError('stored channel result must not be recomputed')

        self.executor = NoChannelCompute(self.distributions, self.tasks,
                                         self.publisher, self.reader)
        self.assertEqual(self.reader.read_result('fixed'), original)
        self.assertEqual(self.reader.read_result('fixed', structured=True), exported)
        self.assertEqual(self.executor.execute_task('fixed'), original)
        self.assertEqual(original.spec.source.source_id, 'channel')
        self.assertEqual(self.tasks.load('fixed').spec, original.spec)
        public = original.to_public_record()
        public['channel'][0][0] = Fraction(99)
        public['event']['Y'] = 0
        copy = self.reader.read_result('fixed', structured=True)
        copy['lower'][0] = 99
        self.assertEqual(self.reader.read_result('fixed', structured=True), exported)

    def test_rollback_and_retry(self):
        class StopBeforeCommit(TaskRepository):
            armed = True

            def mark_completed(self, connection, task_id):
                super().mark_completed(connection, task_id)
                if self.armed:
                    raise RuntimeError('channel stop before commit')

        self.lab[0].close()
        self.lab = make_lab(self.path, StopBeforeCommit)
        (self.database, self.distributions, self.tasks, self.publisher,
         self.reader, self.executor) = self.lab
        revision = self.save_channel('retry', [3, 2, 0], LATENT,
                                     [[1, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]],
                                     {"Y": 1}, {"G": 1})
        with self.assertRaisesRegex(RuntimeError, 'channel stop before commit'):
            self.executor.execute_task('retry')
        self.assertEqual(self.tasks.load('retry').state, 'failed')
        with self.assertRaises(ResultUnavailable):
            self.reader.read_result('retry')
        self.assertEqual(self.database.connection.execute(
            'SELECT COUNT(*) FROM results').fetchone()[0], 0)
        self.tasks.armed = False
        result = self.executor.execute_task('retry')
        self.assertEqual((result.lower, result.upper), (Fraction(0), Fraction(3, 5)))
        self.assertEqual(self.tasks.load('retry').state, 'completed')
