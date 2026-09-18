from __future__ import annotations

import time

from pi_tool.engine.chudnovsky import SeriesState, bs, terms_for_digits
from pi_tool.engine.decimal import pi_prefix_decimal


def measure_one_shot(digits: int, leaf_cutoff: int) -> tuple[float, float]:
    terms = terms_for_digits(digits)
    started = time.perf_counter()
    triple = bs(0, terms, leaf_cutoff)
    split_seconds = time.perf_counter() - started

    state = SeriesState()
    state.restore(terms, [triple])
    started = time.perf_counter()
    pi_prefix_decimal(state, digits)
    extract_seconds = time.perf_counter() - started
    return split_seconds, extract_seconds


def measure_chunked(digits: int, chunk_terms: int) -> float:
    terms = terms_for_digits(digits)
    state = SeriesState()
    started = time.perf_counter()
    remaining = terms
    while remaining > 0:
        step = min(chunk_terms, remaining)
        state.extend(step)
        remaining -= step
    pi_prefix_decimal(state, digits)
    return time.perf_counter() - started


def main() -> None:
    print("== 叶阈值矩阵（一次性 bs + 前缀提取）==")
    print(f"{'digits':>12} {'leaf':>5} {'split_s':>10} {'extract_s':>10}")
    for digits in (10_000, 100_000, 1_000_000):
        for leaf_cutoff in (1, 8, 32, 128):
            split_seconds, extract_seconds = measure_one_shot(digits, leaf_cutoff)
            print(f"{digits:>12,} {leaf_cutoff:>5} {split_seconds:>10.3f} {extract_seconds:>10.3f}")

    print("== 分块策略矩阵（二叉计数树累积，含 total 合并与提取）==")
    print(f"{'digits':>12} {'chunk':>8} {'chunked_s':>10}")
    for digits in (100_000, 1_000_000):
        for chunk_terms in (4_096, 65_536, 262_144):
            seconds = measure_chunked(digits, chunk_terms)
            print(f"{digits:>12,} {chunk_terms:>8,} {seconds:>10.3f}")


if __name__ == "__main__":
    main()
