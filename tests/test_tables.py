from fractions import Fraction
from itertools import product
from random import Random
from test_distribution import LabCase, input_rows
from observatory.analysis.table import ProbabilityTable, validate_table, table_from_frequencies
from observatory.analysis.projection import reorder_table
from observatory.analysis.marginal import marginalize
from observatory.intake.schema import normalize_schema


class TestTables(LabCase):
    def test_reorder_and_mass_conservation(self):
        revision = self.publish_binary()
        table = table_from_frequencies(self.distributions.read_distribution('river',revision).candidate.frequencies)
        reordered = reorder_table(table,['Y','X'])
        self.assertEqual(reordered.rows,(((0,0),Fraction(1,8)),((0,1),Fraction(1,4)),
                                         ((1,0),Fraction(1,8)),((1,1),Fraction(1,2))))
        self.assertEqual(reorder_table(reordered,['X','Y']),table)
        self.assertEqual(marginalize(table,[]).masses,(Fraction(1),))
        self.assertEqual(marginalize(table,['X']).mass,table.mass)
        with self.assertRaises(ValueError):
            reorder_table(table,['Y'])
        with self.assertRaises(ValueError):
            validate_table(ProbabilityTable(table.schema,(Fraction(-1),)*4))
        with self.assertRaises(ValueError):
            validate_table(ProbabilityTable(table.schema,(0.25,)*4))

    def test_independent_integer_enumeration(self):
        rng = Random(817)
        variables = [['A',['off','on']],['B',[0,1,2]],['C',['1',1]]]
        keys = list(product(['off','on'],[0,1,2],['1',1]))
        for trial in range(30):
            counts = [rng.randrange(8) for key in keys]
            counts[0] += 1
            revision = self.distributions.put_distribution('enumerated',str(trial),variables,
                                                            list(reversed(input_rows(variables,counts))))
            outputs = ['C','B'] if trial % 2 else ['B']
            condition = {'A':'on'}
            self.tasks.save_query(str(trial),'enumerated',revision,outputs,condition)
            result = self.executor.execute_task(str(trial))
            denominator = sum(n for key,n in zip(keys,counts) if key[0] == 'on')
            if denominator == 0:
                self.assertEqual(result.status,'zero_condition')
                continue
            expected = []
            domains = [['1',1],[0,1,2]] if trial % 2 else [[0,1,2]]
            for assignment in product(*domains):
                numerator = 0
                for key,n in zip(keys,counts):
                    if key[0] != 'on':
                        continue
                    output_key = (key[2],key[1]) if trial % 2 else (key[1],)
                    if output_key == assignment:
                        numerator += n
                expected.append((assignment,Fraction(numerator,denominator)))
            self.assertEqual(result.rows,tuple(expected))
            self.assertEqual(self.reader.read_result(str(trial)).rows,tuple(expected))
            self.assertEqual(sum(p for key,p in result.rows),Fraction(1))

    def test_empty_schema_is_single_event(self):
        revision = self.distributions.put_distribution('empty','daily',[],[((),7)])
        self.tasks.save_query('empty','empty',revision,[],{})
        result = self.executor.execute_task('empty')
        self.assertEqual(result.rows,(((),Fraction(1)),))
        self.assertEqual(normalize_schema([]),())
