from test_distribution import LabCase, make_lab
from observatory.tasks.repository import TaskRepository
from observatory.tasks.execution import TaskExecutor
from observatory.results.reading import ResultUnavailable


class StopBeforeCommit(TaskRepository):
    armed = True

    def mark_completed(self, connection, task_id):
        super().mark_completed(connection,task_id)
        if self.armed:
            raise RuntimeError('deterministic stop after both writes before commit')


class StopComputing(TaskExecutor):
    armed = True

    def _compute(self, revision, query):
        if self.armed:
            raise ArithmeticError('deterministic computation failure')
        return super()._compute(revision,query)


class StopFailureRecording(TaskRepository):
    def mark_failed(self, task_id, error):
        raise OSError('error record unavailable')


class TestPublication(LabCase):
    def replace_lab(self, task_class=TaskRepository, executor_class=TaskExecutor):
        self.lab[0].close()
        self.lab = make_lab(self.path,task_class,executor_class)
        self.database,self.distributions,self.tasks,self.publisher,self.reader,self.executor = self.lab

    def test_failure_then_retry(self):
        self.replace_lab(StopBeforeCommit)
        task = self.save_binary()
        with self.assertRaisesRegex(RuntimeError,'after both writes'):
            self.executor.execute_task('risk')
        self.assertEqual(self.tasks.load('risk').state,'failed')
        self.assertEqual(self.tasks.load('risk').spec,task.spec)
        self.assertIn('RuntimeError',self.tasks.load('risk').error)
        with self.assertRaises(ResultUnavailable):
            self.reader.read_result('risk')
        self.assertEqual(self.database.connection.execute('SELECT COUNT(*) FROM results').fetchone()[0],0)
        self.tasks.armed = False
        result = self.executor.execute_task('risk')
        self.assertEqual(self.tasks.load('risk').state,'completed')
        self.assertIsNone(self.tasks.load('risk').error)
        self.assertEqual(self.executor.execute_task('risk'),result)
        self.assertEqual(self.database.connection.execute('SELECT COUNT(*) FROM results').fetchone()[0],1)
        self.reopen()
        self.assertEqual(self.reader.read_result('risk'),result)

    def test_compute_failure_and_failed_replay(self):
        self.replace_lab(executor_class=StopComputing)
        task = self.save_binary()
        with self.assertRaisesRegex(ArithmeticError,'computation'):
            self.executor.execute_task('risk')
        failed = self.tasks.load('risk')
        self.assertEqual(failed.state,'failed')
        self.assertEqual(self.tasks.save_query('risk','river',task.spec.revision,['Y'],{'X':1}),failed)
        with self.assertRaises(ResultUnavailable):
            self.reader.read_result('risk')
        self.executor.armed = False
        self.executor.execute_task('risk')
        self.assertEqual(self.tasks.load('risk').state,'completed')

    def test_failure_record_does_not_mask_original(self):
        self.replace_lab(StopFailureRecording,StopComputing)
        task = self.save_binary()
        with self.assertRaisesRegex(ArithmeticError,'computation'):
            self.executor.execute_task('risk')
        self.assertEqual(self.tasks.load('risk'),task)
        with self.assertRaises(ResultUnavailable):
            self.reader.read_result('risk')
        self.executor.armed = False
        self.executor.execute_task('risk')

    def test_completion_requires_publication_transaction(self):
        self.save_binary()
        with self.assertRaises(RuntimeError):
            self.tasks.mark_completed(self.database.connection,'risk')
        self.assertEqual(self.tasks.load('risk').state,'pending')
