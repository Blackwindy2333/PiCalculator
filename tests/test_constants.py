import math

from pi_tool.common.constants import (
    PI_FIRST_100,
    PI_FIRST_1000,
    PI_HEX_FIRST_64,
    DIGITS_PER_TERM,
    stable_digits_for_terms,
    terms_for_digits,
)
from tests.machin_ref import pi_digits_machin


def test_first_100_matches_canonical_value():
    assert PI_FIRST_100 == pi_digits_machin(100)[1:]
    assert PI_FIRST_100.startswith(format(math.pi, ".15f")[2:])


def test_first_1000_frozen_from_independent_algorithm():
    assert PI_FIRST_1000 == pi_digits_machin(1000)[1:]
    assert PI_FIRST_1000.startswith(PI_FIRST_100)


def test_hex_constant_shape():
    assert len(PI_HEX_FIRST_64) == 64
    assert set(PI_HEX_FIRST_64) <= set("0123456789ABCDEF")


def test_terms_and_stable_invariants():
    assert terms_for_digits(1000) >= 1000 / DIGITS_PER_TERM
    assert stable_digits_for_terms(0) == 0
    previous = -1
    for terms in range(0, 1000, 37):
        current = stable_digits_for_terms(terms)
        assert current >= previous
        previous = current
