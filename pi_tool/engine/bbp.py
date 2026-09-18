from __future__ import annotations

from gmpy2 import mpz

COEFFICIENTS = ((1, 4), (4, -2), (5, -1), (6, -1))


def bbp_hex_digits(position: int, count: int) -> str:
    """BBP 公式直接给出 π 小数的十六进制第 position 位起的 count 位（position 从 0 起）。"""
    if position < 0 or count <= 0:
        raise ValueError("position 必须 >= 0，count 必须 > 0")
    precision = 4 * (count + 8)
    scale = mpz(1) << precision
    total = mpz(0)
    for j, coefficient in COEFFICIENTS:
        series = mpz(0)
        for k in range(position + 1):
            denominator = 8 * k + j
            residue = pow(16, position - k, denominator)
            series += (mpz(residue) << precision) // denominator
        for k in range(position + 1, position + count + 9):
            denominator = 8 * k + j
            series += scale // (mpz(16) ** (k - position) * denominator)
        total += coefficient * series
    fraction = total & (scale - 1)
    window = (fraction << (4 * count)) // scale
    return format(int(window), f"0{count}X")
