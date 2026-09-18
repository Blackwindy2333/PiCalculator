from pi_tool.common.constants import PI_HEX_FIRST_64
from pi_tool.engine.bbp import bbp_hex_digits
from pi_tool.engine.chudnovsky import SeriesState, terms_for_digits
from pi_tool.engine.decimal import pi_prefix_hex


def test_matches_known_constant():
    assert bbp_hex_digits(0, 64) == PI_HEX_FIRST_64
    assert bbp_hex_digits(10, 16) == PI_HEX_FIRST_64[10:26]


def test_cross_check_with_engine_at_position_1000():
    state = SeriesState()
    state.extend(terms_for_digits(5000))
    engine_window = pi_prefix_hex(state, 1016)[1000:1016]
    assert bbp_hex_digits(1000, 16) == engine_window


def test_cross_check_with_engine_at_position_100000():
    state = SeriesState()
    state.extend(terms_for_digits(130_000))
    engine_window = pi_prefix_hex(state, 100016)[100000:100016]
    assert bbp_hex_digits(100000, 16) == engine_window
