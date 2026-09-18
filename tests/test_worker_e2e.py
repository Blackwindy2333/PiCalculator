from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)


def _run_worker(args: list[str]) -> None:
    subprocess.run(
        [str(PYTHON), "-m", "pi_tool.engine.worker", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=900,
    )


def _read_session(directory: Path) -> dict:
    return json.loads((directory / "pi.session.json").read_text(encoding="utf-8"))


def test_pause_resume_matches_one_shot(tmp_path):
    target = 100_000
    one_shot = tmp_path / "one"
    _run_worker(["--output-dir", str(one_shot), "--target-digits", str(target)])

    multi = tmp_path / "multi"
    _run_worker(["--output-dir", str(multi), "--target-digits", str(target), "--pause-after-chunks", "1"])
    assert _read_session(multi)["status"] == "paused"
    _run_worker(
        ["--output-dir", str(multi), "--target-digits", str(target), "--resume", "--pause-after-chunks", "1"]
    )
    assert _read_session(multi)["status"] == "paused"
    _run_worker(["--output-dir", str(multi), "--target-digits", str(target), "--resume"])

    assert (one_shot / "pi.txt").read_bytes() == (multi / "pi.txt").read_bytes()
    assert _read_session(one_shot)["sha256_final"] == _read_session(multi)["sha256_final"]


def test_degraded_resume_without_checkpoint(tmp_path):
    target = 50_000
    multi = tmp_path / "multi"
    _run_worker(["--output-dir", str(multi), "--target-digits", str(target), "--pause-after-chunks", "1"])
    (multi / "pi.checkpoint.bin").unlink()
    _run_worker(["--output-dir", str(multi), "--target-digits", str(target), "--resume"])

    one_shot = tmp_path / "one"
    _run_worker(["--output-dir", str(one_shot), "--target-digits", str(target)])
    assert (one_shot / "pi.txt").read_bytes() == (multi / "pi.txt").read_bytes()


def test_line_format_and_prefix(tmp_path):
    target = 100_000
    directory = tmp_path / "one"
    _run_worker(["--output-dir", str(directory), "--target-digits", str(target)])
    text = (directory / "pi.txt").read_text(encoding="ascii")
    assert text.endswith("\n")
    lines = text.split("\n")
    assert lines[-1] == ""
    body = lines[:-1]
    assert len(body[0]) == 1000 and body[0].startswith("3.")
    for line in body[1:-1]:
        assert len(line) == 1000 and line.isdigit()
    assert body[-1].isdigit() and 1 <= len(body[-1]) <= 1000
    digits = "".join(body)
    assert digits.startswith("3.14159265358979323846264338327950288419716939937510")
    session = _read_session(directory)
    assert len(digits) - 2 == session["written_digits"] >= target


def test_session_fields(tmp_path):
    directory = tmp_path / "one"
    _run_worker(["--output-dir", str(directory), "--target-digits", str(20_000)])
    session = _read_session(directory)
    assert session["schema_version"] == 1
    assert session["status"] == "completed"
    assert session["algorithm"] == "chudnovsky-bs-v1"
    assert session["target_digits"] == 20_000
    assert sum(session["digit_counts"]) == session["written_digits"]
    assert len(session["sha256_final"]) == 64
    assert (directory / "pi.checkpoint.bin").exists()
    assert (directory / "pi.log").exists()
