import json
from observatory.intake.schema import normalize_schema
from observatory.archive.provenance import SourceStamp, validate_source_stamp, require_id
from observatory.analysis.query import validate_query
from observatory.tasks.specification import ObservationalTaskSpec

TASK_ENCODING_VERSION = 1


def task_payload(spec):
    return {'version': TASK_ENCODING_VERSION, **spec.to_public_record()}


def encode_task_spec(spec):
    encoded = json.dumps(task_payload(spec), ensure_ascii=True, separators=(',', ':'),
                         allow_nan=False)
    if decode_task_spec(encoded) != spec:
        raise ValueError('noncanonical task specification')
    return encoded


def decode_task_spec(text):
    try:
        data = json.loads(text)
        if type(data['version']) is not int or data['version'] != TASK_ENCODING_VERSION:
            raise ValueError('unsupported task encoding')
        require_id(data['task_id'], 'task_id')
        require_id(data['dataset_id'], 'dataset_id')
        revision = data['revision']
        if type(revision) is not int or revision <= 0:
            raise ValueError('invalid task revision')
        source = SourceStamp(**data['source'])
        validate_source_stamp(source)
        if source.dataset_id != data['dataset_id']:
            raise ValueError('task source mismatch')
        schema = normalize_schema(data['variables'])
        query = validate_query(schema, data['outputs'], data['conditions'])
        return ObservationalTaskSpec(data['task_id'], data['dataset_id'], revision,
                                     source, schema, query)
    except (KeyError, TypeError) as exc:
        raise ValueError('invalid task encoding') from exc
