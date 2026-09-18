import math
from fractions import Fraction

import pytest

from pi_tool.common.constants import terms_for_digits
from pi_tool.engine.chudnovsky import IDENTITY, SeriesState, bs


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


def test_many_small_chunks_equal_single_shot():
    state = SeriesState()
    for _ in range(200):
        state.extend(1)
    reference = bs(0, 200)
    assert (state.triple.p, state.triple.q, state.triple.t) == (reference.p, reference.q, reference.t)


def test_empty_range_is_identity():
    assert bs(5, 5) == IDENTITY
    assert bs(0, 0) == IDENTITY
    state = SeriesState()
    state.extend(0)
    state.extend(-10)
    assert state.terms == 0
    assert state.triple == IDENTITY


def test_reversed_range_and_bad_leaf_cutoff_rejected():
    with pytest.raises(ValueError):
        bs(5, 4)
    with pytest.raises(ValueError):
        bs(0, 10, leaf_cutoff=0)


def test_snapshot_restore_roundtrip():
    state = SeriesState()
    for step in (7, 33, 160):
        state.extend(step)
    terms, levels = state.snapshot()
    restored = SeriesState()
    restored.restore(terms, levels)
    assert restored.terms == state.terms
    assert (restored.triple.p, restored.triple.q, restored.triple.t) == (
        state.triple.p,
        state.triple.q,
        state.triple.t,
    )
    restored.extend(50)
    state.extend(50)
    assert (restored.triple.p, restored.triple.q, restored.triple.t) == (
        state.triple.p,
        state.triple.q,
        state.triple.t,
    )


def test_terms_for_digits_reexport_matches_constants():
    assert terms_for_digits(10000) == int((10000 + 20) / 14.181647462725477) + 3
