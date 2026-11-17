from observatory.intake.batch import prepare_distribution
from observatory.archive.serialization import encode_distribution, decode_distribution
from observatory.archive.provenance import make_source_stamp, SourceStamp, require_id
from observatory.archive.revisions import SourceConflict, UnknownRevision, make_revision


class DistributionRepository:
    def __init__(self, database):
        self.database = database

    def initialize(self):
        with self.database.transaction() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS distributions(
                dataset_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),
                source_id TEXT NOT NULL, digest TEXT NOT NULL, content TEXT NOT NULL,
                PRIMARY KEY(dataset_id, revision), UNIQUE(dataset_id, source_id))""")
            connection.execute("""CREATE TABLE IF NOT EXISTS current_distributions(
                dataset_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                FOREIGN KEY(dataset_id,revision)
                REFERENCES distributions(dataset_id,revision))""")

    def put_distribution(self, dataset_id, source_id, variables, rows):
        candidate = prepare_distribution(variables, rows)
        source = make_source_stamp(dataset_id, source_id, candidate)
        encoded = encode_distribution(candidate)
        with self.database.transaction() as connection:
            previous = connection.execute(
                'SELECT revision,digest,content FROM distributions WHERE dataset_id=? AND source_id=?',
                (dataset_id, source_id)).fetchone()
            if previous:
                if previous[1] != source.digest or previous[2] != encoded:
                    raise SourceConflict('source already registered with different content')
                return previous[0]
            revision = connection.execute(
                'SELECT COALESCE(MAX(revision),0)+1 FROM distributions WHERE dataset_id=?',
                (dataset_id,)).fetchone()[0]
            connection.execute('INSERT INTO distributions VALUES(?,?,?,?,?)',
                               (dataset_id, revision, source_id, source.digest, encoded))
            connection.execute("""INSERT INTO current_distributions VALUES(?,?)
                ON CONFLICT(dataset_id) DO UPDATE SET revision=excluded.revision""",
                               (dataset_id, revision))
        return revision

    def read_distribution(self, dataset_id, revision):
        require_id(dataset_id, 'dataset_id')
        if type(revision) is not int or revision <= 0:
            raise UnknownRevision((dataset_id, revision))
        row = self.database.connection.execute(
            'SELECT source_id,digest,content FROM distributions WHERE dataset_id=? AND revision=?',
            (dataset_id, revision)).fetchone()
        if row is None:
            raise UnknownRevision((dataset_id, revision))
        source = SourceStamp(dataset_id, row[0], row[1])
        return make_revision(revision, decode_distribution(row[2]), source)

    def current_revision(self, dataset_id):
        require_id(dataset_id, 'dataset_id')
        row = self.database.connection.execute(
            'SELECT revision FROM current_distributions WHERE dataset_id=?',
            (dataset_id,)).fetchone()
        if row is None:
            raise UnknownRevision(dataset_id)
        return row[0]
