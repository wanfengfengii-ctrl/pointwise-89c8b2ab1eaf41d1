from fractions import Fraction
from dataclasses import replace
from test_distribution import LabCase, FIXTURES
from observatory.archive.revisions import UnknownRevision
from observatory.tasks.repository import UnknownTask
from observatory.tasks.binding import bind_revision, verify_binding


class TestBinding(LabCase):
    def test_correction_keeps_old_task(self):
        old = self.publish_binary()
        task = self.save_binary('old',old)
        new = self.publish_binary('corrected',FIXTURES['correction']['counts'])
        self.save_binary('new',new)
        old_result = self.executor.execute_task('old')
        new_result = self.executor.execute_task('new')
        self.assertEqual(self.probabilities(old_result),[Fraction(1,3),Fraction(2,3)])
        self.assertEqual(self.probabilities(new_result),[Fraction(5,6),Fraction(1,6)])
        self.assertEqual(old_result.spec.revision,old)
        self.assertEqual(new_result.spec.revision,new)
        self.assertEqual(old_result.spec.source.source_id,'daily')
        self.assertEqual(new_result.spec.source.source_id,'corrected')
        self.assertNotEqual(old_result.spec.source.digest,new_result.spec.source.digest)
        self.assertEqual(self.tasks.load('old').spec,task.spec)
        for task_id, result in [('old',old_result),('new',new_result)]:
            exported = self.reader.read_result(task_id,structured=True)
            self.assertEqual(exported['source'],result.spec.source.to_public_record())
        self.reopen()
        self.assertEqual(self.reader.read_result('old'),old_result)
        self.assertEqual(self.reader.read_result('new'),new_result)

    def test_unknown_revision_and_binding_guard(self):
        self.publish_binary()
        with self.assertRaises(UnknownRevision):
            self.tasks.save_query('missing','river',999,['Y'],{'X':1})
        with self.assertRaises(UnknownTask):
            self.tasks.load('missing')
        task = self.save_binary()
        bound = bind_revision(self.distributions,'river',task.spec.revision)
        self.assertEqual(verify_binding(task.spec,bound),bound.distribution)
        with self.assertRaises(ValueError):
            verify_binding(replace(task.spec,revision=2),bound)
