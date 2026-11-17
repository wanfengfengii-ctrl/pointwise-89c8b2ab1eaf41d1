import json
from observatory.intake.batch import prepare_distribution

REVISION_ENCODING_VERSION = 1


def distribution_payload(candidate):
    return {
        'version': REVISION_ENCODING_VERSION,
        'variables': [[v.name, list(v.domain)] for v in candidate.schema],
        'counts': list(candidate.frequencies.counts),
    }


def encode_distribution(candidate):
    return json.dumps(distribution_payload(candidate), ensure_ascii=True,
                      separators=(',', ':'), allow_nan=False)


def canonical_content_bytes(candidate):
    return encode_distribution(candidate).encode('utf-8')


def decode_distribution(text):
    from observatory.intake.schema import normalize_schema
    from observatory.intake.assignments import enumerate_assignments
    try:
        data = json.loads(text)
        if type(data['version']) is not int or data['version'] != REVISION_ENCODING_VERSION:
            raise ValueError('unsupported distribution encoding')
        schema = normalize_schema(data['variables'])
        keys = enumerate_assignments(schema)
        if len(keys) != len(data['counts']):
            raise ValueError('count width mismatch')
        return prepare_distribution(schema, zip(keys, data['counts']))
    except (KeyError, TypeError) as exc:
        raise ValueError('invalid distribution encoding') from exc
