import json
from fractions import Fraction
from observatory.intake.schema import normalize_schema
from observatory.archive.provenance import SourceStamp, validate_source_stamp, require_id
from observatory.archive.exact import fraction_pair, parse_fraction
from observatory.analysis.query import validate_query
from observatory.analysis.channel import normalize_channel_query
from observatory.tasks.specification import (
    ObservationalTaskSpec, ChannelTaskSpec)

TASK_ENCODING_VERSION = 1
CHANNEL_TASK_ENCODING_VERSION = 2


def task_payload(spec):
    if isinstance(spec, ChannelTaskSpec):
        return {
            'version': CHANNEL_TASK_ENCODING_VERSION, 'kind': 'channel',
            'task_id': spec.task_id, 'dataset_id': spec.dataset_id,
            'revision': spec.revision, 'source': spec.source.to_public_record(),
            'variables': [[v.name, list(v.domain)] for v in spec.schema],
            'latent_variables': [[v.name, list(v.domain)]
                                 for v in spec.latent_schema],
            'channel': [[fraction_pair(value) for value in row]
                        for row in spec.query.channel],
            'event': dict(spec.query.event),
            'condition': dict(spec.query.condition),
        }
    return {'version': TASK_ENCODING_VERSION, **spec.to_public_record()}


def encode_task_spec(spec):
    encoded = json.dumps(task_payload(spec), ensure_ascii=True, separators=(',', ':'),
                         allow_nan=False)
    if decode_task_spec(encoded) != spec:
        raise ValueError('noncanonical task specification')
    return encoded


def _decode_channel_task(data):
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
    latent_schema = normalize_schema(data['latent_variables'])
    channel = tuple(tuple(parse_fraction(cell) for cell in row)
                    for row in data['channel'])
    query = normalize_channel_query(schema, latent_schema, channel,
                                    data['event'], data['condition'])
    return ChannelTaskSpec(data['task_id'], data['dataset_id'], revision,
                           source, schema, query)


def decode_task_spec(text):
    try:
        data = json.loads(text)
        version = data['version']
        if type(version) is not int:
            raise ValueError('unsupported task encoding')
        if version == CHANNEL_TASK_ENCODING_VERSION:
            if data.get('kind') != 'channel':
                raise ValueError('unsupported task encoding')
            return _decode_channel_task(data)
        if version != TASK_ENCODING_VERSION:
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
