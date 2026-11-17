from dataclasses import dataclass
from hashlib import sha256
from observatory.archive.serialization import canonical_content_bytes


def require_id(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError(name + ' must be a nonempty string')
    return value


@dataclass(frozen=True)
class SourceStamp:
    dataset_id: str
    source_id: str
    digest: str

    def to_public_record(self):
        return {'dataset_id': self.dataset_id, 'source_id': self.source_id,
                'digest': self.digest}


def content_digest(candidate):
    return sha256(canonical_content_bytes(candidate)).hexdigest()


def make_source_stamp(dataset_id, source_id, candidate):
    stamp = SourceStamp(require_id(dataset_id, 'dataset_id'),
                        require_id(source_id, 'source_id'), content_digest(candidate))
    validate_source_stamp(stamp)
    return stamp


def validate_source_stamp(stamp, candidate=None):
    require_id(stamp.dataset_id, 'dataset_id')
    require_id(stamp.source_id, 'source_id')
    if (not isinstance(stamp.digest, str) or len(stamp.digest) != 64
            or any(c not in '0123456789abcdef' for c in stamp.digest)):
        raise ValueError('invalid content digest')
    if candidate is not None and content_digest(candidate) != stamp.digest:
        raise ValueError('content does not match source digest')
    return stamp
