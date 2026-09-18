import pickle

from pi_tool.common import protocol
from pi_tool.common.config import Config, load_settings, sanitize, save_settings


def test_config_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    config = Config(target_digits=1234, theme="light", recent_outputs=["a", "b"])
    save_settings(path, config)
    assert load_settings(path) == config


def test_load_missing_or_broken_file_returns_defaults(tmp_path):
    assert load_settings(tmp_path / "nope.json") == Config()
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert load_settings(broken) == Config()


def test_unknown_keys_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"theme": "light", "unknown_key": 1}', encoding="utf-8")
    loaded = load_settings(path)
    assert loaded.theme == "light"


def test_sanitize_clamps_values():
    clean = sanitize(
        Config(
            refresh_interval_s=0.0,
            autosave_interval_s=1,
            memory_limit_gb=0.1,
            view_keep_chars=10,
            target_digits=-5,
            theme="weird",
            rate_unit="x",
            bbp_default_count=999,
            recent_outputs=[str(index) for index in range(50)],
        )
    )
    assert clean.refresh_interval_s >= 0.1
    assert clean.autosave_interval_s >= 10
    assert clean.memory_limit_gb >= 0.5
    assert clean.view_keep_chars >= 10_000
    assert clean.target_digits == 1_000
    assert clean.theme == "dark"
    assert clean.rate_unit == "s"
    assert clean.bbp_default_count == 64
    assert len(clean.recent_outputs) == 20


def test_sanitize_bounds_target_upper():
    assert sanitize(Config(target_digits=10**15)).target_digits == 100_000_000_000


def test_protocol_pickle_roundtrip():
    instances = [
        protocol.PauseCommand(),
        protocol.ResumeRunCommand(),
        protocol.SaveCommand(),
        protocol.StopCommand(),
        protocol.BbpCheckCommand(position=10, count=16),
        protocol.UpdateSettingsCommand(refresh_interval_s=1.0, autosave_interval_s=300.0, memory_limit_bytes=1),
        protocol.ProgressEvent(
            terms_done=1,
            stable_digits=2,
            written_digits=3,
            rate_digits_per_s=4.0,
            eta_seconds=None,
            mem_bytes=5,
            chunk_text="6",
        ),
        protocol.PausedEvent(reason="user", written_digits=7),
        protocol.SavedEvent(path="p", written_digits=8),
        protocol.DoneEvent(total_digits=9, sha256="a" * 64),
        protocol.BbpResultEvent(position=1, count=16, expected="A", got="A", ok=True),
        protocol.ErrorEvent(message="x"),
        protocol.LogEvent(level="info", message="y"),
    ]
    for item in instances:
        assert pickle.loads(pickle.dumps(item)) == item
