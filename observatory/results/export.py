import json
from observatory.results.serialization import fraction_pair


def structured_result(result):
    data = result.to_public_record()
    data['condition_mass'] = fraction_pair(result.condition_mass)
    if result.rows is not None:
        data['rows'] = [
            {'assignment': list(key), 'probability': fraction_pair(probability)}
            for key, probability in result.rows
        ]
    return data


def export_result(result):
    return json.dumps(structured_result(result), ensure_ascii=True,
                      separators=(',', ':'), allow_nan=False)
