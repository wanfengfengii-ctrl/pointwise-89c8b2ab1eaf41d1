import json
from observatory.results.serialization import fraction_pair, ChannelRiskResult


def structured_result(result):
    if isinstance(result, ChannelRiskResult):
        data = result.to_public_record()
        data['channel'] = [[fraction_pair(value) for value in row]
                           for row in data['channel']]
        data['lower'] = None if result.lower is None else fraction_pair(result.lower)
        data['upper'] = None if result.upper is None else fraction_pair(result.upper)
        return data
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
