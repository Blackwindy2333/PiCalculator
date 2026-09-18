import pytest

from pi_tool.common.constants import ALGORITHM_ID, DIGITS_PER_TERM, GUARD_DIGITS, STABLE_MARGIN
from pi_tool.engine import checkpoint
from pi_tool.engine.chudnovsky import SeriesState, bs


def _snapshot(target_digits: int = 100_000) -> dict:
    return {
        "algorithm": ALGORITHM_ID,
        "target_digits": target_digits,
        "digits_per_term": DIGITS_PER_TERM,
        "guard_digits": GUARD_DIGITS,
        "stable_margin": STABLE_MARGIN,
    }


def test_roundtrip_preserves_levels_and_total(tmp_path):
    state = SeriesState()
    for step in (7, 33, 160):
        state.extend(step)
    path = tmp_path / "pi.checkpoint.bin"
    checkpoint.save(path, state, stable_digits=1500, config=_snapshot())
    loaded = checkpoint.load(path, _snapshot())
    assert loaded.terms == 200
    assert loaded.stable_digits == 1500
    restored = SeriesState()
    restored.restore(loaded.terms, loaded.levels)
    assert (restored.triple.p, restored.triple.q, restored.triple.t) == (
        state.triple.p,
        state.triple.q,
        state.triple.t,
    )
    assert [level is None for level in restored.snapshot()[1]] == [
        level is None for level in state.snapshot()[1]
    ]


def test_resume_equals_single_shot(tmp_path):
    state = SeriesState()
    state.extend(100)
    path = tmp_path / "pi.checkpoint.bin"
    checkpoint.save(path, state, stable_digits=1000, config=_snapshot())
    loaded = checkpoint.load(path, _snapshot())
    resumed = SeriesState()
    resumed.restore(loaded.terms, loaded.levels)
    resumed.extend(100)
    reference = bs(0, 200)
    assert (resumed.triple.p, resumed.triple.q, resumed.triple.t) == (
        reference.p,
        reference.q,
        reference.t,
    )


def test_rejects_bad_magic(tmp_path):
    path = tmp_path / "pi.checkpoint.bin"
    checkpoint.save(path, SeriesState(), stable_digits=0, config=_snapshot())
    raw = bytearray(path.read_bytes())
    raw[0] = ord("X")
    path.write_bytes(raw)
    with pytest.raises(checkpoint.CheckpointError):
        checkpoint.load(path, _snapshot())


def test_rejects_truncated_file(tmp_path):
    path = tmp_path / "pi.checkpoint.bin"
    state = SeriesState()
    state.extend(64)
    checkpoint.save(path, state, stable_digits=0, config=_snapshot())
    path.write_bytes(path.read_bytes()[:40])
    with pytest.raises(checkpoint.CheckpointError):
        checkpoint.load(path, _snapshot())


def test_rejects_snapshot_mismatch(tmp_path):
    path = tmp_path / "pi.checkpoint.bin"
    checkpoint.save(path, SeriesState(), stable_digits=0, config=_snapshot(100_000))
    with pytest.raises(checkpoint.CheckpointError):
        checkpoint.load(path, _snapshot(200_000))
