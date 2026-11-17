from dataclasses import dataclass
from fractions import Fraction
from observatory.archive.provenance import validate_source_stamp


class SourceConflict(ValueError):
    pass


class UnknownRevision(LookupError):
    pass


@dataclass(frozen=True)
class DistributionRevision:
    revision: int
    candidate: object
    source: object

    @property
    def schema(self):
        return self.candidate.schema

    def to_public_record(self):
        return {
            'dataset_id': self.source.dataset_id, 'revision': self.revision,
            'source': self.source.to_public_record(),
            'variables': [[v.name, list(v.domain)] for v in self.schema],
            'total': self.candidate.total,
            'rows': [{'assignment': list(key), 'count': count,
                      'probability': Fraction(count, self.candidate.total)}
                     for key, count in self.candidate.frequencies.rows],
        }


def make_revision(revision, candidate, source):
    if type(revision) is not int or revision <= 0:
        raise ValueError('invalid revision number')
    validate_source_stamp(source, candidate)
    return DistributionRevision(revision, candidate, source)
