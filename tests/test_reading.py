from fractions import Fraction
from test_distribution import LabCase, FIXTURES, input_rows
from observatory.tasks.execution import TaskExecutor
from observatory.results.export import export_result
from observatory.results.serialization import encode_result, decode_result


class ReadOnlyExecutor(TaskExecutor):
    def _compute(self, revision, query):
        raise AssertionError('stored result must not be recomputed')


class TestReading(LabCase):
    def test_reopen_and_copy(self):
        variables = [['X',[0,1]],['Y',[0,1]]]
        rows = input_rows(variables,[1,1,2,4])
        revision = self.distributions.put_distribution('river','daily',variables,rows)
        outputs,conditions = ['Y'],{'X':1}
        task = self.tasks.save_query('risk','river',revision,outputs,conditions)
        outputs[:] = ['X']
        conditions['X'] = 0
        variables[0][1].reverse()
        rows[0] = ((0,0),999)
        task_copy = task.to_public_record()
        task_copy['outputs'].clear()
        task_copy['conditions']['X'] = 0
        result = self.executor.execute_task('risk')
        self.assertEqual(self.probabilities(result),[Fraction(1,3),Fraction(2,3)])
        self.assertEqual(decode_result(encode_result(result)),result)
        public = result.to_public_record()
        public['rows'][0]['probability'] = Fraction(99)
        public['source']['source_id'] = 'changed'
        public['conditions']['X'] = 0
        exported = self.reader.read_result('risk',structured=True)
        exported['rows'][0]['probability'][0] = 999
        exported['source']['digest'] = 'changed'
        self.publish_binary('corrected',FIXTURES['correction']['counts'])
        self.reopen()
        self.executor = ReadOnlyExecutor(self.distributions,self.tasks,self.publisher,self.reader)
        self.assertEqual(self.tasks.load('risk').spec,task.spec)
        self.assertEqual(self.reader.read_result('risk'),result)
        self.assertEqual(self.executor.execute_task('risk'),result)
        self.assertIn('"probability":[1,3]',export_result(result))
        self.assertEqual(self.reader.read_result('risk',structured=True)['source']['source_id'],'daily')

    def test_initialization_preserves_correction(self):
        self.save_binary()
        original = self.executor.execute_task('risk')
        corrected = self.publish_binary('corrected',FIXTURES['correction']['counts'])
        for unused in range(2):
            self.distributions.initialize()
            self.tasks.initialize()
            self.publisher.initialize()
            self.assertEqual(self.distributions.current_revision('river'),corrected)
            self.assertEqual(self.reader.read_result('risk'),original)
        self.reopen()
        self.assertEqual(self.distributions.current_revision('river'),corrected)
        self.assertEqual(self.reader.read_result('risk'),original)

    def test_unknown_codec_versions_do_not_reinitialize(self):
        import json
        self.save_binary()
        self.executor.execute_task('risk')
        payload = self.database.connection.execute("SELECT payload FROM results WHERE task_id='risk'").fetchone()[0]
        corrupt = json.loads(payload)
        corrupt['version'] = 2
        with self.database.transaction() as connection:
            connection.execute("UPDATE results SET payload=? WHERE task_id='risk'",(json.dumps(corrupt),))
        self.publisher.initialize()
        with self.assertRaises(ValueError):
            self.reader.read_result('risk')
        stored = self.database.connection.execute("SELECT payload FROM results WHERE task_id='risk'").fetchone()[0]
        self.assertEqual(json.loads(stored)['version'],2)
