from __future__ import annotations

import sys


def arctan_inv(x: int, scale: int) -> int:
    """floor(arctan(1/x) * scale)，独立于 Chudnovsky 的参考算法。"""
    total = 0
    x_squared = x * x
    power = x
    k = 0
    while True:
        term = scale // (power * (2 * k + 1))
        if term == 0:
            break
        total += -term if k & 1 else term
        power *= x_squared
        k += 1
    return total


def pi_digits_machin(digits: int) -> str:
    """Machin 公式：π = 16·arctan(1/5) − 4·arctan(1/239)，返回 '3' + digits 位。"""
    guard = 30
    scale = 10 ** (digits + guard)
    value = 16 * arctan_inv(5, scale) - 4 * arctan_inv(239, scale)
    return str(value)[: digits + 1]


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    print(pi_digits_machin(count))
