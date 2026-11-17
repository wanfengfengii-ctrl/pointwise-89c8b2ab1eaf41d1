from dataclasses import replace
from fractions import Fraction
from test_distribution import LabCase, FIXTURES, input_rows
from observatory.tasks.repository import TaskConflict, UnknownTask
from observatory.results.reading import ResultUnavailable
from observatory.results.publication import candidate_from_outcome
from observatory.analysis.query import run_query, ObservationalQuery


class TestQuery(LabCase):
    def test_exact_conditional(self):
        self.save_binary()
        result = self.executor.execute_task('risk')
        self.assertEqual(self.probabilities(result), [Fraction(1,3), Fraction(2,3)])
        self.assertEqual(result.condition_mass, Fraction(3,4))
        self.assertEqual(result.interpretation, 'observational_conditional_probability')
        self.assertEqual(self.tasks.load('risk').state, 'completed')
        self.assertEqual(self.reader.read_result('risk'), result)

    def test_zero_condition(self):
        revision = self.publish_binary(counts=FIXTURES['zero']['counts'])
        self.save_binary(revision=revision)
        result = self.executor.execute_task('risk')
        self.assertEqual(result.status, 'zero_condition')
        self.assertEqual(result.condition_mass, Fraction())
        self.assertIsNone(result.rows)
        self.assertEqual(self.tasks.load('risk').state, 'completed')
        exported = self.reader.read_result('risk', structured=True)
        self.assertEqual(exported['status'], 'zero_condition')
        self.assertIsNone(exported['rows'])
        self.assertEqual(exported['condition_mass'], [0,1])

    def test_hidden_sum_axis_order_and_empty_queries(self):
        for label in ('hidden', 'reordered'):
            case = FIXTURES[label]
            revision = self.distributions.put_distribution(label, 'daily', case['variables'],
                                                           input_rows(case['variables'], case['counts']))
            outputs = case.get('outputs', ['Y'])
            self.tasks.save_query(label, label, revision, outputs, {'X':1})
            result = self.executor.execute_task(label)
            self.assertEqual(self.probabilities(result), [Fraction(*p) for p in case['expected']])
            if label == 'reordered':
                self.assertEqual([key for key, p in result.rows], [(0,0),(0,1),(1,0),(1,1),(2,0),(2,1)])
        revision = self.publish_binary()
        self.tasks.save_query('marginal', 'river', revision, ['Y'], {})
        self.assertEqual(self.probabilities(self.executor.execute_task('marginal')), [Fraction(3,8),Fraction(5,8)])
        self.tasks.save_query('empty', 'river', revision, [], {'X':1})
        self.assertEqual(self.executor.execute_task('empty').rows, (((),Fraction(1)),))

    def test_task_identity_and_query_rejection(self):
        revision = self.publish_binary()
        a = self.tasks.save_query('empty', 'river', revision, [], {'Y':0,'X':1})
        b = self.tasks.save_query('empty', 'river', revision, [], {'X':1,'Y':0})
        self.assertEqual(a,b)
        self.executor.execute_task('empty')
        self.assertEqual(self.tasks.save_query('empty','river',revision,[],{'X':1,'Y':0}).state, 'completed')
        self.tasks.save_query('joint','river',revision,['X','Y'],{})
        with self.assertRaises(TaskConflict):
            self.tasks.save_query('joint','river',revision,['Y','X'],{})
        for outputs, conditions in ((['Y','Y'],{}), (['missing'],{}), (['X'],{'X':1}),
                                    (['Y'],{'X':True}), (['Y'],{'X':'1'}), (['Y'],{'bad':0})):
            with self.subTest(outputs=outputs,conditions=conditions), self.assertRaises(ValueError):
                self.tasks.save_query('invalid','river',revision,outputs,conditions)
        with self.assertRaises(UnknownTask):
            self.executor.execute_task('unknown')
        with self.assertRaises(ResultUnavailable):
            self.reader.read_result('unknown')

    def test_result_guard(self):
        task = self.save_binary()
        revision = self.distributions.read_distribution('river',task.spec.revision)
        good = candidate_from_outcome(task, run_query(revision,task.spec.query))
        source = replace(task.spec.source, source_id='wrong')
        specs = [
            replace(task.spec,task_id='wrong'), replace(task.spec,revision=2),
            replace(task.spec,source=source),
            replace(task.spec,query=ObservationalQuery(('X',),())),
            replace(task.spec,query=ObservationalQuery(('Y',),(('X',0),))),
        ]
        bad = [replace(good,spec=spec) for spec in specs]
        bad += [replace(good,rows=(None,None)), replace(good,rows=good.rows[:-1]),
                replace(good,rows=(good.rows[0],good.rows[0])),
                replace(good,rows=tuple(reversed(good.rows))),
                replace(good,rows=(((0,),Fraction(1,4)),((1,),Fraction(1,2)))),
                replace(good,rows=(((0,),-Fraction(1)),((1,),Fraction(2)))),
                replace(good,rows=(((0,),0.5),((1,),0.5))),
                replace(good,status='zero_condition',condition_mass=Fraction()),
                replace(good,status='computable',condition_mass=Fraction(),rows=None),
                replace(good,interpretation='causal_effect')]
        for candidate in bad:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                self.publisher.publish('risk',candidate)
            self.assertEqual(self.tasks.load('risk').state,'pending')
            with self.assertRaises(ResultUnavailable):
                self.reader.read_result('risk')
        self.publisher.publish('risk',good)
        self.assertEqual(self.reader.read_result('risk'),good)
