from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PauseCommand:
    pass


@dataclass(frozen=True)
class ResumeRunCommand:
    pass


@dataclass(frozen=True)
class SaveCommand:
    pass


@dataclass(frozen=True)
class StopCommand:
    pass


@dataclass(frozen=True)
class BbpCheckCommand:
    position: int
    count: int


@dataclass(frozen=True)
class UpdateSettingsCommand:
    refresh_interval_s: float
    autosave_interval_s: float
    memory_limit_bytes: int


@dataclass(frozen=True)
class ProgressEvent:
    terms_done: int
    stable_digits: int
    written_digits: int
    rate_digits_per_s: float
    eta_seconds: float | None
    mem_bytes: int
    chunk_text: str


@dataclass(frozen=True)
class PausedEvent:
    reason: str
    written_digits: int


@dataclass(frozen=True)
class SavedEvent:
    path: str
    written_digits: int


@dataclass(frozen=True)
class DoneEvent:
    total_digits: int
    sha256: str


@dataclass(frozen=True)
class BbpResultEvent:
    position: int
    count: int
    expected: str
    got: str
    ok: bool


@dataclass(frozen=True)
class ErrorEvent:
    message: str


@dataclass(frozen=True)
class LogEvent:
    level: str
    message: str
