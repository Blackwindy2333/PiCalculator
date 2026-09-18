from __future__ import annotations

import gmpy2
from gmpy2 import mpz

from ..common.constants import GUARD_DIGITS, stable_digits_for_terms
from .chudnovsky import SeriesState

HEX_TO_DECIMAL_RATIO = 1.20412


class NotEnoughTerms(Exception):
    """稳定位数不足，无法提取指定长度的前缀。"""


def _require_stable(state: SeriesState, digits: int) -> None:
    stable = stable_digits_for_terms(state.terms)
    if stable < digits:
        raise NotEnoughTerms(f"稳定位数 {stable} < 需要 {digits}")


def pi_prefix_decimal(state: SeriesState, digits: int) -> str:
    """稳定前缀的十进制小数位（不含 "3."），长度恰为 digits。"""
    if digits <= 0:
        return ""
    _require_stable(state, digits)
    m = digits + GUARD_DIGITS
    root = gmpy2.isqrt(mpz(10005) * mpz(10) ** (2 * m))
    value = (426880 * root * state.triple.q) // state.triple.t
    return str(value)[1 : 1 + digits]


def pi_prefix_hex(state: SeriesState, hex_digits: int) -> str:
    """稳定前缀的十六进制小数位（大写），长度恰为 hex_digits。"""
    if hex_digits <= 0:
        return ""
    _require_stable(state, int(hex_digits * HEX_TO_DECIMAL_RATIO) + 8)
    h = hex_digits + 12
    root = gmpy2.isqrt(mpz(10005) * mpz(16) ** (2 * h))
    value = (426880 * root * state.triple.q) // state.triple.t
    return _mpz_to_base16(value)[1 : 1 + hex_digits]


def _mpz_to_base16(value: mpz) -> str:
    try:
        return value.digits(16).upper()
    except AttributeError:
        pass
    try:
        return gmpy2.digits(value, 16).upper()
    except AttributeError:
        return format(int(value), "X")
