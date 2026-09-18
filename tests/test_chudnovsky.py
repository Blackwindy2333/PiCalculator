import math
from fractions import Fraction

import pytest

from pi_tool.common.constants import DIGITS_PER_TERM, stable_digits_for_terms, terms_for_digits
from pi_tool.engine.chudnovsky import SeriesState, bs


def _naive_sum(terms: int) -> Fraction:
    total = Fraction(0)
    for k in range(terms):
        term = Fraction(
            math.factorial(6 * k) * (13591409 + 545140134 * k),
            math.factorial(3 * k) * math.factorial(k) ** 3 * 640320 ** (3 * k),
        )
        total += -term if k & 1 else term
    return total


@pytest.mark.parametrize("terms", [1, 2, 3, 7, 16, 50])
def test_binary_splitting_matches_naive_sum(terms):
    state = SeriesState()
    state.extend(terms, leaf_cutoff=1)
    assert Fraction(state.triple.t, state.triple.q) == _naive_sum(terms)


def test_leaf_cutoff_does_not_change_result():
    fast = bs(0, 200, leaf_cutoff=32)
    slow = bs(0, 200, leaf_cutoff=1)
    assert (fast.p, fast.q, fast.t) == (slow.p, slow.q, slow.t)


def test_chunked_state_equals_single_shot():
    state = SeriesState()
    for step in (-5, 0, 1, 5, 39, 155):
        state.extend(step)
    reference = bs(0, 200)
    assert state.terms == 200
    assert (state.triple.p, state.triple.q, state.triple.t) == (reference.p, reference.q, reference.t)


def test_terms_and_stable_monotonic():
    assert terms_for_digits(10000) == int((10000 + 20) / DIGITS_PER_TERM) + 3
    previous = -1
    for terms in range(0, 1000, 37):
        current = stable_digits_for_terms(terms)
        assert current >= previous
        previous = current
