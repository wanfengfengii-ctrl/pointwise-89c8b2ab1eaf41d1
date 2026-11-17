from observatory.analysis.query import run_query
from observatory.tasks.binding import bind_revision, verify_binding
from observatory.results.publication import candidate_from_outcome
from observatory.results.reading import ResultUnavailable


class TaskExecutor:
    def __init__(self, distributions, tasks, publisher, reader):
        database = tasks.database
        if any(owner.database is not database for owner in (distributions, publisher, reader)):
            raise ValueError('execution requires shared repositories')
        self.distributions = distributions
        self.tasks = tasks
        self.publisher = publisher
        self.reader = reader

    def _compute(self, revision, query):
        return run_query(revision, query)

    def execute_task(self, task_id):
        task = self.tasks.load(task_id)
        try:
            return self.reader.read_result(task_id)
        except ResultUnavailable:
            pass
        try:
            if task.state == 'completed':
                raise ValueError('completed task is missing its result')
            bound = bind_revision(self.distributions, task.spec.dataset_id, task.spec.revision)
            revision = verify_binding(task.spec, bound)
            outcome = self._compute(revision, task.spec.query)
            self.publisher.publish(task_id, candidate_from_outcome(task, outcome))
            return self.reader.read_result(task_id)
        except Exception as exc:
            try:
                self.tasks.mark_failed(task_id, type(exc).__name__ + ': ' + str(exc))
            except Exception:
                pass
            raise
