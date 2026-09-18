from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..common.config import Config


@dataclass(frozen=True)
class SessionInfo:
    directory: str
    target_digits: int
    written_digits: int
    status: str
    updated_at: str
    file_size: int
    sha256_prefix: str


def scan_sessions(directories: list[str]) -> list[SessionInfo]:
    found: list[SessionInfo] = []
    for directory in directories:
        base = Path(directory)
        session_path = base / "pi.session.json"
        text_file = base / "pi.txt"
        if not session_path.exists():
            continue
        try:
            raw = json.loads(session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sha = raw.get("sha256_final") or ""
        found.append(
            SessionInfo(
                directory=str(base),
                target_digits=int(raw.get("target_digits", 0)),
                written_digits=int(raw.get("written_digits", 0)),
                status=str(raw.get("status", "unknown")),
                updated_at=str(raw.get("updated_at", "")),
                file_size=text_file.stat().st_size if text_file.exists() else 0,
                sha256_prefix=sha[:16],
            )
        )
    found.sort(key=lambda item: item.updated_at, reverse=True)
    return found


def remember_output(config: Config, directory: str) -> Config:
    target = str(Path(directory))
    config.recent_outputs = [target] + [item for item in config.recent_outputs if item != target]
    config.recent_outputs = config.recent_outputs[:20]
    return config
