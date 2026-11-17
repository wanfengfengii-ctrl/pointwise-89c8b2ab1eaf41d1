from dataclasses import dataclass
from fractions import Fraction
import json
from observatory.tasks.serialization import task_payload, decode_task_spec
from observatory.tasks.specification import ChannelTaskSpec
from observatory.analysis.query import OBSERVATIONAL_INTERPRETATION
from observatory.analysis.channel import CHANNEL_INTERPRETATION
from observatory.archive.exact import fraction_pair, parse_fraction

RESULT_ENCODING_VERSION = 1
CHANNEL_RESULT_ENCODING_VERSION = 2

__all__ = ['fraction_pair', 'parse_fraction',
           'RiskResult', 'ChannelRiskResult',
           'encode_result', 'decode_result']


@dataclass(frozen=True)
class RiskResult:
    spec: object
    status: str
    condition_mass: Fraction
    rows: object
    interpretation: str = OBSERVATIONAL_INTERPRETATION

    def to_public_record(self):
        return {
            **self.spec.to_public_record(), 'status': self.status,
            'condition_mass': self.condition_mass, 'interpretation': self.interpretation,
            'rows': None if self.rows is None else [
                {'assignment': list(key), 'probability': value} for key, value in self.rows
            ],
        }


@dataclass(frozen=True)
class ChannelRiskResult:
    spec: object
    status: str
    lower: object
    upper: object
    interpretation: str = CHANNEL_INTERPRETATION

    def to_public_record(self):
        return {
            **self.spec.to_public_record(), 'interpretation': self.interpretation,
            'status': self.status, 'lower': self.lower, 'upper': self.upper,
        }


def encode_result(result):
    if isinstance(result, ChannelRiskResult):
        payload = {
            'version': CHANNEL_RESULT_ENCODING_VERSION, 'kind': 'channel',
            'specification': task_payload(result.spec),
            'status': result.status, 'interpretation': result.interpretation,
            'lower': None if result.lower is None else fraction_pair(result.lower),
            'upper': None if result.upper is None else fraction_pair(result.upper),
        }
    else:
        payload = {
            'version': RESULT_ENCODING_VERSION, 'specification': task_payload(result.spec),
            'status': result.status, 'interpretation': result.interpretation,
            'condition_mass': fraction_pair(result.condition_mass),
            'rows': None if result.rows is None else [
                [list(key), fraction_pair(value)] for key, value in result.rows],
        }
    return json.dumps(payload, ensure_ascii=True, separators=(',', ':'),
                      allow_nan=False)


def decode_result(text):
    try:
        data = json.loads(text)
        version = data['version']
        if type(version) is not int:
            raise ValueError('unsupported result encoding')
        if version == CHANNEL_RESULT_ENCODING_VERSION:
            if data.get('kind') != 'channel':
                raise ValueError('unsupported result encoding')
            spec = decode_task_spec(json.dumps(data['specification']))
            if not isinstance(spec, ChannelTaskSpec):
                raise ValueError('channel result requires a channel task')
            lower = None if data['lower'] is None else parse_fraction(data['lower'])
            upper = None if data['upper'] is None else parse_fraction(data['upper'])
            return ChannelRiskResult(spec, data['status'], lower, upper,
                                     data['interpretation'])
        if version != RESULT_ENCODING_VERSION:
            raise ValueError('unsupported result encoding')
        spec = decode_task_spec(json.dumps(data['specification']))
        if isinstance(spec, ChannelTaskSpec):
            raise ValueError('observational result encoding for channel task')
        rows = None if data['rows'] is None else tuple(
            (tuple(key), parse_fraction(value)) for key, value in data['rows'])
        return RiskResult(spec, data['status'], parse_fraction(data['condition_mass']),
                          rows, data['interpretation'])
    except (TypeError, KeyError) as exc:
        raise ValueError('invalid result encoding') from exc
