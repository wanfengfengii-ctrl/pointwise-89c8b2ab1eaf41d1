from test_distribution import LabCase, FIXTURES, input_rows
from observatory.archive.revisions import SourceConflict


class TestSource(LabCase):
    def test_replay_and_conflict(self):
        revision = self.publish_binary()
        case = FIXTURES['binary']
        rows = input_rows(case['variables'], case['counts'])
        self.assertEqual(self.distributions.put_distribution('river', 'daily',
                         case['variables'], reversed(rows)), revision)
        with self.assertRaises(SourceConflict):
            self.publish_binary(counts=[1,1,2,5])
        self.assertEqual(self.distributions.read_distribution('river', revision).candidate.total, 8)
        self.assertEqual(self.database.connection.execute('SELECT COUNT(*) FROM distributions').fetchone()[0], 1)

    def test_canonical_axes_old_source_and_dataset_scope(self):
        original = self.publish_binary()
        corrected = self.publish_binary('correction', FIXTURES['correction']['counts'])
        self.assertEqual(self.publish_binary(), original)
        self.assertEqual(self.distributions.current_revision('river'), corrected)
        case = FIXTURES['binary']
        rows = input_rows(case['variables'], case['counts'])
        swapped = [((key[1], key[0]), count) for key, count in rows]
        with self.assertRaises(SourceConflict):
            self.distributions.put_distribution('river', 'daily', list(reversed(case['variables'])), swapped)
        other = self.distributions.put_distribution('other', 'daily', case['variables'],
                                                    input_rows(case['variables'], [3,2,1,4]))
        self.assertEqual(other, 1)
        self.assertEqual(self.distributions.current_revision('river'), corrected)
        self.assertNotEqual(self.distributions.read_distribution('other', other).source.digest,
                            self.distributions.read_distribution('river', original).source.digest)
