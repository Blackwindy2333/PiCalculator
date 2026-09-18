from __future__ import annotations

import json
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from gmpy2 import mpz

from .chudnovsky import SeriesState, Triple

MAGIC = b"PICK2"
VERSION = 2


class CheckpointError(Exception):
    pass


@dataclass(frozen=True)
class Checkpoint:
    terms: int
    stable_digits: int
    levels: list[Triple | None]
    config: dict


def _read_exact(handle: BinaryIO, length: int) -> bytes:
    chunks = []
    remaining = length
    while remaining:
        block = handle.read(remaining)
        if not block:
            raise CheckpointError("检查点文件被截断")
        chunks.append(block)
        remaining -= len(block)
    return b"".join(chunks)


def _mpz_to_raw(value: mpz) -> bytes:
    length = (value.bit_length() + 7) // 8
    if length == 0:
        return b""
    try:
        return value.to_bytes(length, "big")
    except AttributeError:
        return int(value).to_bytes(length, "big")


def _raw_to_mpz(raw: bytes) -> mpz:
    if not raw:
        return mpz(0)
    return mpz(int.from_bytes(raw, "big"))


def _write_mpz(handle: BinaryIO, value: mpz) -> None:
    raw = _mpz_to_raw(value)
    handle.write(struct.pack("<Q", len(raw)))
    handle.write(raw)


def _read_mpz(handle: BinaryIO) -> mpz:
    (length,) = struct.unpack("<Q", _read_exact(handle, 8))
    return _raw_to_mpz(_read_exact(handle, length))


def save(path: Path, state: SeriesState, stable_digits: int, config: dict) -> None:
    """把运行态（计量树各层）原子写入检查点文件。"""
    terms, levels = state.snapshot()
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "wb") as handle:
        handle.write(MAGIC)
        handle.write(struct.pack("<IQQ", VERSION, terms, stable_digits))
        handle.write(struct.pack("<I", len(levels)))
        for level in levels:
            if level is None:
                handle.write(struct.pack("<B", 0))
                continue
            handle.write(struct.pack("<B", 1))
            _write_mpz(handle, level.p)
            _write_mpz(handle, level.q)
            _write_mpz(handle, level.t)
        raw_config = json.dumps(config, ensure_ascii=False, sort_keys=True).encode("utf-8")
        handle.write(struct.pack("<I", len(raw_config)))
        handle.write(raw_config)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def load(path: Path, expected: dict) -> Checkpoint:
    with open(path, "rb") as handle:
        if _read_exact(handle, len(MAGIC)) != MAGIC:
            raise CheckpointError("检查点 magic 不匹配")
        version, terms, stable_digits = struct.unpack("<IQQ", _read_exact(handle, 20))
        if version != VERSION:
            raise CheckpointError(f"检查点版本不支持: {version}")
        (level_count,) = struct.unpack("<I", _read_exact(handle, 4))
        levels: list[Triple | None] = []
        for _ in range(level_count):
            (present,) = struct.unpack("<B", _read_exact(handle, 1))
            if present:
                levels.append(Triple(_read_mpz(handle), _read_mpz(handle), _read_mpz(handle)))
            else:
                levels.append(None)
        (config_length,) = struct.unpack("<I", _read_exact(handle, 4))
        config = json.loads(_read_exact(handle, config_length).decode("utf-8"))
    for key, value in expected.items():
        if config.get(key) != value:
            raise CheckpointError(f"检查点口径不一致: {key}")
    return Checkpoint(terms, stable_digits, levels, config)
