import argparse
from fractions import Fraction
from itertools import product
from pathlib import Path
import json
from observatory.archive.storage import ArchiveDatabase
from observatory.archive.repository import DistributionRepository
from observatory.tasks.repository import TaskRepository
from observatory.tasks.execution import TaskExecutor
from observatory.results.publication import ResultPublisher
from observatory.results.reading import ResultReader


def open_lab(path):
    database = ArchiveDatabase.open(path)
    try:
        distributions = DistributionRepository(database)
        distributions.initialize()
        tasks = TaskRepository(database, distributions)
        tasks.initialize()
        publisher = ResultPublisher(database, tasks)
        publisher.initialize()
        reader = ResultReader(database, tasks)
        executor = TaskExecutor(distributions, tasks, publisher, reader)
        return database, distributions, tasks, reader, executor
    except BaseException:
        database.close()
        raise


def run_demo(path):
    if str(path) == ':memory:':
        raise ValueError('demo requires a file database to demonstrate reopening')
    fixtures = json.loads((Path(__file__).resolve().parent / 'fixtures.json').read_text())
    case = fixtures['binary']
    variables = case['variables']
    assignments = list(product(*(domain for name, domain in variables)))
    database, distributions, tasks, reader, executor = open_lab(path)
    try:
        old_revision = distributions.put_distribution(
            'river-demo', 'daily', variables, zip(assignments, case['counts']))
        tasks.save_query('old-risk', 'river-demo', old_revision, ['Y'], {'X':1})
        new_revision = distributions.put_distribution(
            'river-demo', 'corrected', variables,
            zip(assignments, fixtures['correction']['counts']))
        tasks.save_query('new-risk', 'river-demo', new_revision, ['Y'], {'X':1})
        old = executor.execute_task('old-risk')
        new = executor.execute_task('new-risk')
        expected_old = [Fraction(1,3), Fraction(2,3)]
        expected_new = [Fraction(5,6), Fraction(1,6)]
        assert [p for key,p in old.rows] == expected_old
        assert [p for key,p in new.rows] == expected_new
        assert old.spec.source.source_id == 'daily'
        assert new.spec.source.source_id == 'corrected'
        assert distributions.current_revision('river-demo') == new_revision
        old_export = reader.read_result('old-risk', structured=True)
        new_export = reader.read_result('new-risk', structured=True)
    finally:
        database.close()
    database, distributions, tasks, reader, executor = open_lab(path)
    try:
        assert reader.read_result('old-risk') == old
        assert reader.read_result('new-risk') == new
        assert reader.read_result('old-risk', structured=True) == old_export
        assert reader.read_result('new-risk', structured=True) == new_export
        downstream_expected = {
            'old_revision':old_revision, 'new_revision':new_revision,
            'old_source':'daily', 'new_source':'corrected',
            'old_probabilities':[[1,3],[2,3]], 'new_probabilities':[[5,6],[1,6]],
        }
        downstream_actual = {
            'old_revision':old_export['revision'], 'new_revision':new_export['revision'],
            'old_source':old_export['source']['source_id'],
            'new_source':new_export['source']['source_id'],
            'old_probabilities':[row['probability'] for row in old_export['rows']],
            'new_probabilities':[row['probability'] for row in new_export['rows']],
        }
        assert downstream_actual == downstream_expected
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id':'v1_fixed_revision',
            'input':{'variables':variables, 'original_counts':case['counts'],
                     'corrected_counts':fixtures['correction']['counts'],
                     'outputs':['Y'], 'conditions':{'X':1}},
            'expected':{'old':[str(p) for p in expected_old],
                        'new':[str(p) for p in expected_new]},
            'actual':{'old':[str(p) for key,p in old.rows],
                      'new':[str(p) for key,p in new.rows]},
            'downstream_expected':downstream_expected,
            'downstream_actual':downstream_actual,
            'code_paths':['observatory/archive/repository.py',
                          'observatory/tasks/binding.py',
                          'observatory/tasks/execution.py',
                          'observatory/analysis/conditional.py',
                          'observatory/results/publication.py',
                          'observatory/results/reading.py'],
            'oracle':'Independent integer sums: old 2/(2+4),4/(2+4); correction 5/(5+1),1/(5+1).'
        }, ensure_ascii=False, separators=(',', ':')))
        return downstream_actual
    finally:
        database.close()


def main():
    parser = argparse.ArgumentParser(description='Publish and reproduce exact observational risk reports')
    parser.add_argument('--database', required=True, help='explicit demo SQLite file; stable IDs are replayed')
    args = parser.parse_args()
    run_demo(args.database)


if __name__ == '__main__':
    main()
