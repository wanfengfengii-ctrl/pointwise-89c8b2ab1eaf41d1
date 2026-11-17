from test_distribution import LabCase, FIXTURES, input_rows
from observatory.intake.assignments import assignment_position


class TestIntake(LabCase):
    def assert_rejected(self, variables, rows):
        before = self.database.connection.execute('SELECT COUNT(*) FROM distributions').fetchone()[0]
        with self.assertRaises(ValueError):
            self.distributions.put_distribution('river', 'invalid', variables, rows)
        self.assertEqual(self.database.connection.execute('SELECT COUNT(*) FROM distributions').fetchone()[0], before)
        self.assertEqual(self.distributions.current_revision('river'), 1)

    def test_reject_incomplete_batch(self):
        self.publish_binary()
        case = FIXTURES['binary']
        rows = input_rows(case['variables'], case['counts'])
        self.assert_rejected(case['variables'], rows[:-1])

    def test_duplicate_hole_and_count_domain(self):
        self.publish_binary()
        case = FIXTURES['binary']
        rows = input_rows(case['variables'], case['counts'])
        self.assert_rejected(case['variables'], rows[:-1] + [rows[0]])
        for count in (-1, True, 1.5, None):
            changed = list(rows)
            changed[0] = (changed[0][0], count)
            with self.subTest(count=count):
                self.assert_rejected(case['variables'], changed)
        self.assert_rejected(case['variables'], input_rows(case['variables'], [0,0,0,0]))

    def test_schema_domain_and_assignments(self):
        self.publish_binary()
        for schema in ([['X',[0,1]],['X',[0,1]]], [['X',[]]], [['X',[0,0]]],
                       [['X',[False,1]]], [['X',[None]]], [['X',[1.0]]], [['',[0]]]):
            with self.subTest(schema=schema):
                self.assert_rejected(schema, [])
        case = FIXTURES['binary']
        for assignment in ((0,2), (True,0), {'X':0}, {'X':0,'Y':0,'Z':0}, ('0',0)):
            rows = input_rows(case['variables'], case['counts'])
            rows[0] = (assignment, 1)
            self.assert_rejected(case['variables'], rows)
        self.assertEqual(assignment_position(case['variables'], {'Y':1,'X':0}), 1)
