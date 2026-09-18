import pytest

from pi_tool.common.constants import PI_FIRST_1000, PI_HEX_FIRST_64
from pi_tool.engine.chudnovsky import SeriesState, terms_for_digits
from pi_tool.engine.decimal import NotEnoughTerms, pi_prefix_decimal, pi_prefix_hex


def _state_for(digits: int) -> SeriesState:
    state = SeriesState()
    state.extend(terms_for_digits(digits))
    return state


def test_prefix_1000_matches_frozen_constant():
    assert pi_prefix_decimal(_state_for(1000), 1000) == PI_FIRST_1000


def test_prefix_10000_extends_1000():
    assert pi_prefix_decimal(_state_for(10_000), 10_000).startswith(PI_FIRST_1000)


def test_prefix_is_stable_across_requested_lengths():
    state = _state_for(3000)
    assert pi_prefix_decimal(state, 2000).startswith(pi_prefix_decimal(state, 1000))


def test_prefix_independent_of_state_progress():
    assert pi_prefix_decimal(_state_for(2000), 1000) == pi_prefix_decimal(_state_for(5000), 1000)


def test_prefix_independent_of_chunking():
    chunked = SeriesState()
    for step in (37, 401, 5, 6690, 2000):
        chunked.extend(step)
    assert pi_prefix_decimal(chunked, 1000) == PI_FIRST_1000


def test_hex_prefix_matches_constant():
    assert pi_prefix_hex(_state_for(1000), 64) == PI_HEX_FIRST_64


def test_raises_when_not_enough_terms():
    state = SeriesState()
    state.extend(1)
    with pytest.raises(NotEnoughTerms):
        pi_prefix_decimal(state, 1000)
    with pytest.raises(NotEnoughTerms):
        pi_prefix_hex(state, 64)


def test_zero_length_requests_return_empty():
    assert pi_prefix_decimal(SeriesState(), 0) == ""
    assert pi_prefix_hex(SeriesState(), 0) == ""
