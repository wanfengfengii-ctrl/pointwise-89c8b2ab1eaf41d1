from dataclasses import dataclass
from observatory.archive.provenance import require_id
from observatory.tasks.binding import bind_revision
from observatory.tasks.specification import (
    normalize_task_spec, normalize_channel_task_spec, same_task_spec)
from observatory.tasks.serialization import encode_task_spec, decode_task_spec


class TaskConflict(ValueError):
    pass


class UnknownTask(LookupError):
    pass


@dataclass(frozen=True)
class TaskRecord:
    spec: object
    state: str
    error: object = None

    def to_public_record(self):
        return {**self.spec.to_public_record(), 'state': self.state, 'error': self.error}


class TaskRepository:
    def __init__(self, database, distributions):
        if distributions.database is not database:
            raise ValueError('repositories must share a database')
        self.database = database
        self.distributions = distributions

    def initialize(self):
        with self.database.transaction() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS tasks(
                task_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL,
                revision INTEGER NOT NULL, specification TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','failed','completed')),
                error TEXT, FOREIGN KEY(dataset_id,revision)
                REFERENCES distributions(dataset_id,revision))""")

    def save_query(self, task_id, dataset_id, revision, outputs, conditions):
        bound = bind_revision(self.distributions, dataset_id, revision)
        spec = normalize_task_spec(task_id, bound.distribution, outputs, conditions)
        return self._save_spec(spec)

    def save_channel_query(self, task_id, dataset_id, revision, latent_variables,
                           channel, event, condition):
        bound = bind_revision(self.distributions, dataset_id, revision)
        spec = normalize_channel_task_spec(task_id, bound.distribution,
                                           latent_variables, channel, event,
                                           condition)
        return self._save_spec(spec)

    def _save_spec(self, spec):
        encoded = encode_task_spec(spec)
        with self.database.transaction() as connection:
            row = connection.execute('SELECT specification FROM tasks WHERE task_id=?',
                                     (spec.task_id,)).fetchone()
            if row:
                if not same_task_spec(decode_task_spec(row[0]), spec):
                    raise TaskConflict('task ID already has a different fixed specification')
            else:
                connection.execute('INSERT INTO tasks VALUES(?,?,?,?,?,NULL)',
                                   (spec.task_id, spec.dataset_id, spec.revision,
                                    encoded, 'pending'))
        return self.load(spec.task_id)

    def load(self, task_id):
        require_id(task_id, 'task_id')
        row = self.database.connection.execute(
            'SELECT specification,state,error,dataset_id,revision FROM tasks WHERE task_id=?',
            (task_id,)).fetchone()
        if row is None:
            raise UnknownTask(task_id)
        spec = decode_task_spec(row[0])
        if (spec.task_id, spec.dataset_id, spec.revision) != (task_id, row[3], row[4]):
            raise ValueError('task storage identity mismatch')
        if row[1] not in ('pending', 'failed', 'completed'):
            raise ValueError('invalid task state')
        return TaskRecord(spec, row[1], row[2])

    def mark_completed(self, connection, task_id):
        if connection is not self.database.connection or not connection.in_transaction:
            raise RuntimeError('completion requires the shared publication transaction')
        self.load(task_id)
        connection.execute("UPDATE tasks SET state='completed',error=NULL WHERE task_id=?",
                           (task_id,))

    def mark_failed(self, task_id, error):
        self.load(task_id)
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE tasks SET state='failed',error=? WHERE task_id=? AND state!='completed'",
                (str(error)[:1000], task_id))
