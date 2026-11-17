from fractions import Fraction
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from observatory.archive.storage import ArchiveDatabase
from observatory.archive.repository import DistributionRepository
from observatory.tasks.repository import TaskRepository
from observatory.results.publication import ResultPublisher
from observatory.results.reading import ResultReader
from observatory.tasks.execution import TaskExecutor
from observatory.analysis.table import table_from_frequencies

FIXTURES = json.loads((Path(__file__).resolve().parents[1] / 'fixtures.json').read_text())


def input_rows(variables, counts):
    return list(zip(product(*(domain for name, domain in variables)), counts))


def make_lab(path, task_class=TaskRepository, executor_class=TaskExecutor):
    database = ArchiveDatabase.open(path)
    try:
        distributions = DistributionRepository(database)
        distributions.initialize()
        tasks = task_class(database, distributions)
        tasks.initialize()
        publisher = ResultPublisher(database, tasks)
        publisher.initialize()
        reader = ResultReader(database, tasks)
        executor = executor_class(distributions, tasks, publisher, reader)
        return database, distributions, tasks, publisher, reader, executor
    except BaseException:
        database.close()
        raise


class LabCase(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix='river-observatory-')
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / 'archive.sqlite3')
        self.lab = make_lab(self.path)
        self.addCleanup(lambda: self.lab[0].close())
        self.database, self.distributions, self.tasks, self.publisher, self.reader, self.executor = self.lab

    def publish_binary(self, source='daily', counts=None):
        case = FIXTURES['binary']
        return self.distributions.put_distribution(
            'river', source, case['variables'],
            input_rows(case['variables'], case['counts'] if counts is None else counts))

    def save_binary(self, task_id='risk', revision=None):
        if revision is None:
            revision = self.publish_binary()
        return self.tasks.save_query(task_id, 'river', revision, ['Y'], {'X': 1})

    def probabilities(self, result):
        return [value for key, value in result.rows]

    def reopen(self):
        self.lab[0].close()
        self.lab = make_lab(self.path)
        self.database, self.distributions, self.tasks, self.publisher, self.reader, self.executor = self.lab


class TestDistribution(LabCase):
    def test_complete_binary_table(self):
        revision = self.publish_binary()
        stored = self.distributions.read_distribution('river', revision)
        self.assertEqual(stored.candidate.total, 8)
        self.assertEqual([v.name for v in stored.schema], ['X', 'Y'])
        table = table_from_frequencies(stored.candidate.frequencies)
        self.assertEqual(table.masses, (Fraction(1,8), Fraction(1,8), Fraction(1,4), Fraction(1,2)))
        self.assertEqual(stored.to_public_record()['rows'][3]['probability'], Fraction(1,2))
        self.assertEqual(self.distributions.current_revision('river'), revision)

    def test_schema_roundtrip_and_exact_codec(self):
        from observatory.archive.serialization import encode_distribution, decode_distribution
        from observatory.results.serialization import parse_fraction
        variables = [['device', ['1', 1]], ['weather', ['wet', 'dry', 'wind']]]
        counts = [10**30 + 1, 0, 2, 3, 4, 5]
        revision = self.distributions.put_distribution('typed', 'source', variables,
                                                       input_rows(variables, counts))
        variables[0][1].reverse()
        stored = self.distributions.read_distribution('typed', revision)
        self.assertEqual(stored.schema[0].domain, ('1', 1))
        self.assertEqual(stored.candidate.frequencies.counts, tuple(counts))
        self.assertEqual(decode_distribution(encode_distribution(stored.candidate)), stored.candidate)
        record = stored.to_public_record()
        record['variables'][0][1].clear()
        record['rows'][0]['count'] = -1
        self.reopen()
        self.assertEqual(self.distributions.read_distribution('typed', revision), stored)
        for pair in ([1,0], [1,-2], [True,2], [1.0,2]):
            with self.subTest(pair=pair), self.assertRaises(ValueError):
                parse_fraction(pair)

    def test_storage_version_rejected(self):
        import sqlite3
        other = str(Path(self.directory.name) / 'future.sqlite3')
        connection = sqlite3.connect(other)
        connection.execute('PRAGMA user_version = 2')
        connection.close()
        with self.assertRaises(ValueError):
            ArchiveDatabase.open(other)
