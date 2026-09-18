from __future__ import annotations

import hashlib
from pathlib import Path

from .bbp import bbp_hex_digits
from .chudnovsky import SeriesState
from .decimal import pi_prefix_hex


def prefix_matches(computed: str, reference: str) -> bool:
    return computed.startswith(reference)


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while block := handle.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def bbp_crosscheck(state: SeriesState, position: int, count: int) -> tuple[str, str, bool]:
    expected = bbp_hex_digits(position, count)
    window = pi_prefix_hex(state, position + count)
    got = window[position : position + count]
    return expected, got, expected == got
