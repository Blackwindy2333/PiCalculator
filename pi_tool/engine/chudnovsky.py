from __future__ import annotations

from dataclasses import dataclass

from gmpy2 import mpz

from ..common.constants import (
    C3_OVER_24,
    LEAF_CUTOFF_INITIAL,
    stable_digits_for_terms as stable_digits_for_terms,
    terms_for_digits as terms_for_digits,
)


@dataclass(frozen=True)
class Triple:
    p: mpz
    q: mpz
    t: mpz


IDENTITY = Triple(mpz(1), mpz(1), mpz(0))


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


def merge(left: Triple, right: Triple) -> Triple:
    return Triple(
        left.p * right.p,
        left.q * right.q,
        left.t * right.q + left.p * right.t,
    )


def _leaf_range(a: int, b: int) -> Triple:
    node = _leaf(a)
    for k in range(a + 1, b):
        node = merge(node, _leaf(k))
    return node


def bs(a: int, b: int, leaf_cutoff: int = LEAF_CUTOFF_INITIAL) -> Triple:
    """项区间 [a, b) 的二分分裂结果；空区间返回恒等元，逆序区间报错。"""
    if leaf_cutoff < 1:
        raise ValueError("leaf_cutoff 必须 >= 1")
    if b < a:
        raise ValueError("bs 区间必须满足 a <= b")
    if b == a:
        return IDENTITY
    if b - a <= leaf_cutoff:
        return _leaf_range(a, b)
    middle = (a + b) // 2
    return merge(bs(a, middle, leaf_cutoff), bs(middle, b, leaf_cutoff))


class SeriesState:
    """项区间 [0, terms) 的运行态；π = 426880·√10005·Q/T。

    内部以二叉计数树保存各已完成块（只合并同规模的相邻块），因此单次
    extend 的合并开销只与本次块大小有关、与已完成项数无关——块大小可以
    取小到 ~1 秒（暂停/刷新粒度），总合并开销仍是 O(M(N)) 量级。
    """

    def __init__(self) -> None:
        self.terms = 0
        self._levels: list[Triple | None] = []
        self._total: Triple | None = None

    def extend(self, extra_terms: int, leaf_cutoff: int = LEAF_CUTOFF_INITIAL) -> None:
        """把项区间 [terms, terms+extra_terms) 并入运行态；extra_terms <= 0 时不动。"""
        if extra_terms <= 0:
            return
        chunk = bs(self.terms, self.terms + extra_terms, leaf_cutoff)
        self.terms += extra_terms
        carry = chunk
        level = 0
        while True:
            if level == len(self._levels):
                self._levels.append(carry)
                break
            occupied = self._levels[level]
            if occupied is None:
                self._levels[level] = carry
                break
            carry = merge(occupied, carry)
            self._levels[level] = None
            level += 1
        self._total = None

    @property
    def triple(self) -> Triple:
        if self._total is None:
            total: Triple | None = None
            for level in reversed(self._levels):
                if level is not None:
                    total = level if total is None else merge(total, level)
            self._total = total if total is not None else IDENTITY
        return self._total

    def snapshot(self) -> tuple[int, list[Triple | None]]:
        return self.terms, list(self._levels)

    def restore(self, terms: int, levels: list[Triple | None]) -> None:
        self.terms = terms
        self._levels = list(levels)
        self._total = None


__all__ = [
    "Triple",
    "SeriesState",
    "bs",
    "merge",
    "stable_digits_for_terms",
    "terms_for_digits",
]
