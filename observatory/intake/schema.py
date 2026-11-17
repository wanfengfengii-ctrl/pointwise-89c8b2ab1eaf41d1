from dataclasses import dataclass
from math import prod


def valid_label(value):
    return isinstance(value, str) or type(value) is int


@dataclass(frozen=True)
class VariableSpec:
    name: str
    domain: tuple

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise ValueError('variable name must be a nonempty string')
        if isinstance(self.domain, (str, bytes)):
            raise ValueError('domain must be a sequence of labels')
        try:
            domain = tuple(self.domain)
        except TypeError as exc:
            raise ValueError('invalid domain') from exc
        if not domain or any(not valid_label(v) for v in domain):
            raise ValueError('domain labels must be strings or non-boolean integers')
        if len(set(domain)) != len(domain):
            raise ValueError('duplicate domain label')
        object.__setattr__(self, 'domain', domain)


def normalize_schema(variables):
    if isinstance(variables, (str, bytes, dict)):
        raise ValueError('schema must be an ordered sequence')
    try:
        result = tuple(
            VariableSpec(v.name, v.domain) if isinstance(v, VariableSpec)
            else VariableSpec(*v) for v in variables
        )
    except (TypeError, AttributeError) as exc:
        raise ValueError('invalid schema') from exc
    if len({v.name for v in result}) != len(result):
        raise ValueError('duplicate variable name')
    return result


def schema_cardinality(schema):
    return prod(len(v.domain) for v in normalize_schema(schema))
