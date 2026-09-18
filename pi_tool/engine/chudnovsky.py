from __future__ import annotations

from dataclasses import dataclass

from gmpy2 import mpz

from ..common.constants import (
    C3_OVER_24,
    DIGITS_PER_TERM,
    GUARD_DIGITS,
    LEAF_CUTOFF_INITIAL,
    STABLE_MARGIN,
    stable_digits_for_terms,
    terms_for_digits,
)


@dataclass(frozen=True)
class Triple:
    p: mpz
    q: mpz
    t: mpz


def _leaf(a: int) -> Triple:
    if a == 0:
        p = q = mpz(1)
    else:
        p = mpz(6 * a - 5) * (2 * a - 1) * (6 * a - 1)
        q = mpz(a) ** 3 * C3_OVER_24
    t = p * (13591409 + 545140134 * a)
    if a & 1:
        t = -t
    return Triple(p, q, t)


def _leaf_range(a: int, b: int) -> Triple:
    node = _leaf(a)
    for k in range(a + 1, b):
        child = _leaf(k)
        node = Triple(
            node.p * child.p,
            node.q * child.q,
            node.t * child.q + node.p * child.t,
        )
    return node


def merge(left: Triple, right: Triple) -> Triple:
    return Triple(
        left.p * right.p,
        left.q * right.q,
        left.t * right.q + left.p * right.t,
    )


def bs(a: int, b: int, leaf_cutoff: int = LEAF_CUTOFF_INITIAL) -> Triple:
    if b - a <= leaf_cutoff:
        return _leaf_range(a, b)
    middle = (a + b) // 2
    return merge(bs(a, middle, leaf_cutoff), bs(middle, b, leaf_cutoff))


class SeriesState:
    """项区间 [0, terms) 的运行态：π = 426880·√10005·Q/T。"""

    def __init__(self) -> None:
        self.terms = 0
        self.triple = Triple(mpz(1), mpz(1), mpz(0))

    def extend(self, extra_terms: int, leaf_cutoff: int = LEAF_CUTOFF_INITIAL) -> None:
        if extra_terms <= 0:
            return
        chunk = bs(self.terms, self.terms + extra_terms, leaf_cutoff)
        self.triple = merge(self.triple, chunk)
        self.terms += extra_terms


__all__ = [
    "Triple",
    "SeriesState",
    "bs",
    "merge",
    "stable_digits_for_terms",
    "terms_for_digits",
]
