from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

TARGET_DIGITS_MIN = 1_000
TARGET_DIGITS_MAX = 100_000_000_000
THEMES = {"dark", "light"}
RATE_UNITS = {"s", "m"}


@dataclass
class Config:
    theme: str = "dark"
    output_dir: str = "output"
    target_digits: int = 10_000_000
    refresh_interval_s: float = 1.0
    autosave_interval_s: int = 300
    memory_limit_gb: float = 8.0
    view_keep_chars: int = 200_000
    rate_unit: str = "s"
    bbp_default_hex_position: int = 1_000_000
    bbp_default_count: int = 16
    recent_outputs: list[str] = field(default_factory=list)


def sanitize(config: Config) -> Config:
    if config.theme not in THEMES:
        config.theme = "dark"
    if config.rate_unit not in RATE_UNITS:
        config.rate_unit = "s"
    config.target_digits = min(max(config.target_digits, TARGET_DIGITS_MIN), TARGET_DIGITS_MAX)
    config.refresh_interval_s = max(config.refresh_interval_s, 0.1)
    config.autosave_interval_s = max(config.autosave_interval_s, 10)
    config.memory_limit_gb = max(config.memory_limit_gb, 0.5)
    config.view_keep_chars = max(config.view_keep_chars, 10_000)
    config.bbp_default_hex_position = max(config.bbp_default_hex_position, 0)
    config.bbp_default_count = min(max(config.bbp_default_count, 1), 64)
    config.recent_outputs = list(config.recent_outputs[:20])
    return config


def load_settings(path: Path) -> Config:
    if not path.exists():
        return sanitize(Config())
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return sanitize(Config())
    known = {key: value for key, value in raw.items() if key in Config.__dataclass_fields__}
    return sanitize(Config(**known))


def save_settings(path: Path, config: Config) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
