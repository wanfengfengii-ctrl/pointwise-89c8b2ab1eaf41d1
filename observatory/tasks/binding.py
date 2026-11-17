from dataclasses import dataclass
from observatory.archive.provenance import validate_source_stamp


@dataclass(frozen=True)
class BoundDistribution:
    distribution: object

    @property
    def revision(self):
        return self.distribution.revision

    @property
    def source(self):
        return self.distribution.source


def bind_revision(repository, dataset_id, revision):
    return BoundDistribution(repository.read_distribution(dataset_id, revision))


def verify_binding(spec, bound):
    revision = bound.distribution
    validate_source_stamp(revision.source, revision.candidate)
    if (spec.dataset_id != revision.source.dataset_id
            or spec.revision != revision.revision
            or spec.source != revision.source or spec.schema != revision.schema):
        raise ValueError('distribution does not match fixed task binding')
    return revision
