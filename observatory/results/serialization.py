from dataclasses import dataclass
from fractions import Fraction
import json
from observatory.tasks.serialization import task_payload, decode_task_spec
from observatory.analysis.query import OBSERVATIONAL_INTERPRETATION

RESULT_ENCODING_VERSION = 1


def fraction_pair(value):
    if not isinstance(value, Fraction):
        raise ValueError('probability must be a Fraction')
    return [value.numerator, value.denominator]


def parse_fraction(pair):
    if (not isinstance(pair, list) or len(pair) != 2
            or any(type(n) is not int for n in pair) or pair[1] <= 0):
        raise ValueError('invalid exact fraction encoding')
    return Fraction(*pair)


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


def encode_result(result):
    payload = {
        'version': RESULT_ENCODING_VERSION, 'specification': task_payload(result.spec),
        'status': result.status, 'interpretation': result.interpretation,
        'condition_mass': fraction_pair(result.condition_mass),
        'rows': None if result.rows is None else [
            [list(key), fraction_pair(value)] for key, value in result.rows],
    }
    return json.dumps(payload, ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def decode_result(text):
    try:
        data = json.loads(text)
        if type(data['version']) is not int or data['version'] != RESULT_ENCODING_VERSION:
            raise ValueError('unsupported result encoding')
        spec = decode_task_spec(json.dumps(data['specification']))
        rows = None if data['rows'] is None else tuple(
            (tuple(key), parse_fraction(value)) for key, value in data['rows'])
        return RiskResult(spec, data['status'], parse_fraction(data['condition_mass']),
                          rows, data['interpretation'])
    except (TypeError, KeyError) as exc:
        raise ValueError('invalid result encoding') from exc
