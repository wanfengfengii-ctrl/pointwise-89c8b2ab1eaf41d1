from observatory.archive.provenance import require_id
from observatory.results.serialization import decode_result
from observatory.results.validation import validate_result
from observatory.results.export import structured_result


class ResultUnavailable(LookupError):
    pass


class ResultReader:
    def __init__(self, database, tasks):
        if tasks.database is not database:
            raise ValueError('reading and tasks must share a database')
        self.database = database
        self.tasks = tasks

    def read_result(self, task_id, structured=False):
        require_id(task_id, 'task_id')
        row = self.database.connection.execute(
            'SELECT payload FROM results WHERE task_id=?', (task_id,)).fetchone()
        if row is None:
            raise ResultUnavailable(task_id)
        task = self.tasks.load(task_id)
        if task.state != 'completed':
            raise ValueError('result exists without completed task')
        result = validate_result(task, decode_result(row[0]))
        return structured_result(result) if structured else result
