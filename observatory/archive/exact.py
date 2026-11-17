"""Lossless Fraction pair encoding shared by task and result payloads."""
from fractions import Fraction


def fraction_pair(value):
    if not isinstance(value, Fraction):
        raise ValueError('probability must be a Fraction')
    return [value.numerator, value.denominator]


def parse_fraction(pair):
    if (not isinstance(pair, list) or len(pair) != 2
            or any(type(n) is not int for n in pair) or pair[1] <= 0):
        raise ValueError('invalid exact fraction encoding')
    return Fraction(*pair)
