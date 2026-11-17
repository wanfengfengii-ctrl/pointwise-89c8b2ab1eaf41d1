from observatory.results.serialization import RiskResult, encode_result, decode_result
from observatory.results.validation import validate_result


def candidate_from_outcome(task, outcome):
    rows = None if outcome.table is None else outcome.table.rows
    return RiskResult(task.spec, outcome.status, outcome.condition_mass, rows)


class ResultPublisher:
    def __init__(self, database, tasks):
        if tasks.database is not database:
            raise ValueError('publication and tasks must share a database')
        self.database = database
        self.tasks = tasks

    def initialize(self):
        with self.database.transaction() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS results(
                task_id TEXT PRIMARY KEY REFERENCES tasks(task_id),
                payload TEXT NOT NULL)""")

    def publish(self, task_id, candidate):
        task = self.tasks.load(task_id)
        validate_result(task, candidate)
        encoded = encode_result(candidate)
        validate_result(task, decode_result(encoded))
        with self.database.transaction() as connection:
            previous = connection.execute('SELECT payload FROM results WHERE task_id=?',
                                          (task_id,)).fetchone()
            if previous:
                result = decode_result(previous[0])
                validate_result(task, result)
                if result != candidate or task.state != 'completed':
                    raise ValueError('immutable result conflict')
                return result
            if task.state == 'completed':
                raise ValueError('completed task is missing its result')
            connection.execute('INSERT INTO results VALUES(?,?)', (task_id, encoded))
            self.tasks.mark_completed(connection, task_id)
        return decode_result(encoded)
