from dataclasses import dataclass
from observatory.analysis.query import validate_query
from observatory.archive.provenance import require_id


@dataclass(frozen=True)
class ObservationalTaskSpec:
    task_id: str
    dataset_id: str
    revision: int
    source: object
    schema: tuple
    query: object

    def to_public_record(self):
        return {
            'task_id': self.task_id, 'dataset_id': self.dataset_id,
            'revision': self.revision, 'source': self.source.to_public_record(),
            'variables': [[v.name, list(v.domain)] for v in self.schema],
            **self.query.to_public_record(),
        }


def normalize_task_spec(task_id, revision, outputs, conditions):
    require_id(task_id, 'task_id')
    return ObservationalTaskSpec(
        task_id, revision.source.dataset_id, revision.revision, revision.source,
        revision.schema, validate_query(revision.schema, outputs, conditions))


def same_task_spec(left, right):
    return left == right
