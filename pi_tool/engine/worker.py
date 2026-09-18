from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import queue
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import psutil

from ..common.constants import (
    ALGORITHM_ID,
    DIGITS_PER_TERM,
    GUARD_DIGITS,
    LEAF_CUTOFF_INITIAL,
    PI_FIRST_100,
    STABLE_MARGIN,
    stable_digits_for_terms,
    terms_for_digits,
)
from ..common.protocol import (
    BbpCheckCommand,
    BbpResultEvent,
    DoneEvent,
    ErrorEvent,
    LogEvent,
    PauseCommand,
    PausedEvent,
    ProgressEvent,
    ResumeRunCommand,
    SaveCommand,
    SavedEvent,
    StopCommand,
    UpdateSettingsCommand,
)
from . import checkpoint as checkpoint_module
from .chudnovsky import SeriesState, bs
from .decimal import NotEnoughTerms, pi_prefix_decimal
from .verify import bbp_crosscheck, sha256_file

LINE_WIDTH = 1000
CHUNK_TARGET_SECONDS = 0.75
CHUNK_MIN_TERMS = 1_024
CHUNK_MAX_SECONDS = 2.0
INITIAL_CHUNK_TERMS = 4_096
MIN_REFRESH_STEP = 100_000
FSYNC_THRESHOLD_BYTES = 16 * 1024 * 1024
PROGRESS_INTERVAL_SECONDS = 0.15
LOG_MAX_BYTES = 5 * 1024 * 1024


def insert_linebreaks(text: str, stream_chars_before: int, width: int = LINE_WIDTH) -> str:
    """在字符流每累计 width 个字符后插入换行（stream_chars_before 为已写入流长度）。"""
    pieces: list[str] = []
    cursor = 0
    position = stream_chars_before
    while cursor < len(text):
        boundary = (position // width + 1) * width
        take = min(boundary - position, len(text) - cursor)
        pieces.append(text[cursor : cursor + take])
        cursor += take
        position += take
        if position % width == 0:
            pieces.append("\n")
    return "".join(pieces)


class DigitFile:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None
        self.written_digits = 0
        self.unsynced_bytes = 0

    def open(self, resume_written: int | None) -> int:
        if resume_written is None or not self.path.exists():
            self.handle = open(self.path, "wb")
            self.handle.write(b"3.")
            self.written_digits = 0
            return 0
        stream_length = 2 + resume_written
        expected_bytes = stream_length + stream_length // LINE_WIDTH
        self.handle = open(self.path, "r+b")
        size = os.fstat(self.handle.fileno()).st_size
        if size < expected_bytes:
            self.handle.truncate(0)
            self.handle.seek(0)
            self.handle.write(b"3.")
            self.written_digits = 0
            return 0
        self.handle.truncate(expected_bytes)
        self.handle.seek(expected_bytes)
        self.written_digits = resume_written
        return resume_written

    def append(self, digits: str) -> None:
        text = insert_linebreaks(digits, 2 + self.written_digits)
        self.handle.write(text.encode("ascii"))
        self.written_digits += len(digits)
        self.unsynced_bytes += len(text)
        if self.unsynced_bytes >= FSYNC_THRESHOLD_BYTES:
            self.flush_sync()

    def flush_sync(self) -> None:
        if self.handle is None:
            return
        self.handle.flush()
        os.fsync(self.handle.fileno())
        self.unsynced_bytes = 0

    def finalize(self) -> None:
        if self.handle is None:
            return
        if (2 + self.written_digits) % LINE_WIDTH != 0:
            self.handle.write(b"\n")
        self.flush_sync()
        self.handle.close()
        self.handle = None


def write_session(path: Path, payload: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


class Calculator:
    def __init__(
        self,
        events,
        output_dir: Path,
        target_digits: int,
        refresh_interval_s: float,
        autosave_interval_s: float,
        memory_limit_bytes: int,
    ) -> None:
        self.events = events
        self.output_dir = output_dir
        self.target_digits = target_digits
        self.refresh_interval_s = refresh_interval_s
        self.autosave_interval_s = autosave_interval_s
        self.memory_limit_bytes = memory_limit_bytes
        self.state = SeriesState()
        self.target_terms = terms_for_digits(target_digits)
        self.planned_stable = stable_digits_for_terms(self.target_terms)
        self.min_refresh_step = max(1_000, min(MIN_REFRESH_STEP, self.planned_stable // 4))
        self.digit_file = DigitFile(output_dir / "pi.txt")
        self.session_path = output_dir / "pi.session.json"
        self.checkpoint_path = output_dir / "pi.checkpoint.bin"
        self.started_at = time.perf_counter()
        self.elapsed_before = 0.0
        self.chunk_rates: deque[tuple[int, float]] = deque(maxlen=20)
        self.last_progress_at = 0.0
        self.last_refresh_at = 0.0
        self.last_refresh_stable = 0
        self.next_refresh_not_before = 0.0
        self.last_autosave_at = time.perf_counter()
        self.digit_counts = [0] * 10
        self.status = "running"
        self.process = psutil.Process()
        self.chunks_done = 0
        self.pending_chunk_text = ""
        self.sha256_final: str | None = None
        self.created_at = datetime.now().astimezone().isoformat(timespec="seconds")

    # ---------- 状态与统计 ----------

    def elapsed(self) -> float:
        return self.elapsed_before + (time.perf_counter() - self.started_at)

    def term_rate(self) -> float:
        total_terms = sum(terms for terms, _ in self.chunk_rates)
        total_time = sum(seconds for _, seconds in self.chunk_rates)
        return total_terms / total_time if total_time > 0 else 0.0

    def digit_rate(self) -> float:
        return self.term_rate() * DIGITS_PER_TERM

    def eta_seconds(self) -> float | None:
        remaining = self.target_terms - self.state.terms
        if remaining <= 0:
            return 0.0
        rate = self.term_rate()
        return remaining / rate if rate > 0 else None

    def next_chunk_terms(self) -> int:
        remaining = self.target_terms - self.state.terms
        rate = self.term_rate()
        if rate <= 0:
            return min(INITIAL_CHUNK_TERMS, remaining)
        target = int(rate * CHUNK_TARGET_SECONDS)
        cap = max(CHUNK_MIN_TERMS, int(rate * CHUNK_MAX_SECONDS))
        return max(1, min(target, cap, remaining))

    # ---------- 日志 ----------

    def emit_log(self, level: str, message: str) -> None:
        self.events.put(LogEvent(level=level, message=message))
        line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} [{level}] {message}\n"
        log_path = self.output_dir / "pi.log"
        try:
            if log_path.exists() and log_path.stat().st_size > LOG_MAX_BYTES:
                for index in range(2, 0, -1):
                    source = log_path.with_name(f"pi.log.{index}")
                    if source.exists():
                        source.replace(log_path.with_name(f"pi.log.{index + 1}"))
                log_path.replace(log_path.with_name("pi.log.1"))
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError:
            pass

    # ---------- 数字写出 ----------

    def count_digits(self, text: str) -> None:
        for digit in "0123456789":
            self.digit_counts[int(digit)] += text.count(digit)

    def append_stable_digits(self) -> None:
        stable = stable_digits_for_terms(self.state.terms)
        if stable <= self.digit_file.written_digits:
            return
        prefix = pi_prefix_decimal(self.state, stable)
        new_digits = prefix[self.digit_file.written_digits :]
        self.digit_file.append(new_digits)
        self.count_digits(new_digits)
        self.pending_chunk_text += new_digits
        self.last_refresh_stable = stable

    def maybe_refresh(self) -> None:
        stable = stable_digits_for_terms(self.state.terms)
        if stable <= self.digit_file.written_digits:
            return
        required_step = max(self.min_refresh_step, self.last_refresh_stable // 100)
        if stable - self.last_refresh_stable < required_step:
            return
        now = time.perf_counter()
        if now < self.next_refresh_not_before or now - self.last_refresh_at < self.refresh_interval_s:
            return
        started = time.perf_counter()
        self.append_stable_digits()
        cost = time.perf_counter() - started
        self.last_refresh_at = time.perf_counter()
        if cost > 0.25:
            self.next_refresh_not_before = time.perf_counter() + 4 * cost

    # ---------- 事件 ----------

    def maybe_emit_progress(self, force: bool = False) -> None:
        now = time.perf_counter()
        if not force and now - self.last_progress_at < PROGRESS_INTERVAL_SECONDS:
            return
        self.last_progress_at = now
        chunk_text = self.pending_chunk_text
        self.pending_chunk_text = ""
        self.events.put(
            ProgressEvent(
                terms_done=self.state.terms,
                stable_digits=stable_digits_for_terms(self.state.terms),
                written_digits=self.digit_file.written_digits,
                rate_digits_per_s=self.digit_rate(),
                eta_seconds=self.eta_seconds(),
                mem_bytes=self.process.memory_info().rss,
                chunk_text=chunk_text,
            )
        )

    # ---------- 持久化 ----------

    def snapshot_config(self) -> dict:
        return {
            "algorithm": ALGORITHM_ID,
            "target_digits": self.target_digits,
            "digits_per_term": DIGITS_PER_TERM,
            "guard_digits": GUARD_DIGITS,
            "stable_margin": STABLE_MARGIN,
        }

    def persist_session(self, status: str | None = None) -> None:
        payload = {
            "schema_version": 1,
            "status": status or self.status,
            "algorithm": ALGORITHM_ID,
            "target_digits": self.target_digits,
            "written_digits": self.digit_file.written_digits,
            "stable_digits": stable_digits_for_terms(self.state.terms),
            "terms_done": self.state.terms,
            "elapsed_seconds": round(self.elapsed(), 2),
            "created_at": self.created_at,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "output_file": "pi.txt",
            "digit_counts": list(self.digit_counts),
            "sha256_final": self.sha256_final,
        }
        write_session(self.session_path, payload)

    def save_all(self, session_status: str | None = None) -> None:
        stable = stable_digits_for_terms(self.state.terms)
        checkpoint_module.save(self.checkpoint_path, self.state, stable, self.snapshot_config())
        self.digit_file.flush_sync()
        self.persist_session(session_status)

    # ---------- 恢复 ----------

    def resume_from_disk(self) -> bool:
        if not self.session_path.exists():
            self.digit_file.open(resume_written=None)
            return False
        session = json.loads(self.session_path.read_text(encoding="utf-8"))
        self.digit_counts = list(session.get("digit_counts") or [0] * 10)
        self.elapsed_before = float(session.get("elapsed_seconds", 0.0))
        written = int(session.get("written_digits", 0))
        actual = self.digit_file.open(resume_written=written)
        if actual == 0 and written > 0:
            self.digit_counts = [0] * 10
            self.emit_log("warning", "pi.txt 与记录不一致，已从头重写数字")
        try:
            loaded = checkpoint_module.load(self.checkpoint_path, self.snapshot_config())
        except (OSError, checkpoint_module.CheckpointError) as error:
            terms_done = int(session.get("terms_done", 0))
            levels = [bs(0, terms_done)] if terms_done > 0 else []
            self.state.restore(terms_done, levels)
            self.emit_log("warning", f"检查点不可用（{error}），已降级重演到第 {terms_done:,} 项")
            return True
        self.state.restore(loaded.terms, loaded.levels)
        self.emit_log("info", f"已从检查点恢复：第 {loaded.terms:,} 项 / 已写 {self.digit_file.written_digits:,} 位")
        return True

    # ---------- 命令 ----------

    def apply_settings(self, command: UpdateSettingsCommand) -> None:
        self.refresh_interval_s = max(command.refresh_interval_s, 0.1)
        self.autosave_interval_s = max(command.autosave_interval_s, 10.0)
        self.memory_limit_bytes = max(command.memory_limit_bytes, 1)

    def run_bbp_check(self, command: BbpCheckCommand) -> None:
        self.emit_log("info", f"BBP 校验开始：十六进制第 {command.position:,} 位（{command.count} 位）")
        started = time.perf_counter()
        try:
            expected, got, ok = bbp_crosscheck(self.state, command.position, command.count)
        except NotEnoughTerms:
            self.events.put(ErrorEvent(message="尚未计算到该位置，请先继续计算"))
            return
        self.events.put(
            BbpResultEvent(position=command.position, count=command.count, expected=expected, got=got, ok=ok)
        )
        verdict = "一致" if ok else "不一致"
        self.emit_log("info", f"BBP 校验完成（{time.perf_counter() - started:.1f} 秒）：{verdict}")

    def pause_and_save(self) -> None:
        self.status = "paused"
        self.append_stable_digits()
        self.save_all(session_status="paused")
        self.maybe_emit_progress(force=True)
        self.emit_log("info", f"已暂停并保存：{self.digit_file.written_digits:,} 位")

    def wait_while_paused(self, commands) -> str:
        while True:
            command = commands.get(block=True)
            if isinstance(command, ResumeRunCommand):
                self.status = "running"
                self.emit_log("info", "继续计算")
                return "continue"
            if isinstance(command, StopCommand):
                self.status = "stopped"
                self.persist_session("stopped")
                self.emit_log("info", "已停止（进度已保存，可随时继续）")
                return "stop"
            if isinstance(command, SaveCommand):
                self.save_all()
                self.events.put(
                    SavedEvent(path=str(self.session_path), written_digits=self.digit_file.written_digits)
                )
            if isinstance(command, BbpCheckCommand):
                self.run_bbp_check(command)
            if isinstance(command, UpdateSettingsCommand):
                self.apply_settings(command)

    def dispatch(self, command, commands) -> str:
        if isinstance(command, PauseCommand):
            self.pause_and_save()
            self.events.put(PausedEvent(reason="user", written_digits=self.digit_file.written_digits))
            return self.wait_while_paused(commands)
        if isinstance(command, StopCommand):
            self.pause_and_save()
            self.status = "stopped"
            self.persist_session("stopped")
            return "stop"
        if isinstance(command, SaveCommand):
            self.append_stable_digits()
            self.save_all()
            self.events.put(SavedEvent(path=str(self.session_path), written_digits=self.digit_file.written_digits))
            return "continue"
        if isinstance(command, BbpCheckCommand):
            self.run_bbp_check(command)
            return "continue"
        if isinstance(command, UpdateSettingsCommand):
            self.apply_settings(command)
            return "continue"
        return "continue"

    def poll_commands(self, commands, blocking: bool) -> str:
        while True:
            try:
                command = commands.get(block=blocking, timeout=None if blocking else 0.0)
            except queue.Empty:
                return "continue"
            action = self.dispatch(command, commands)
            if action != "continue":
                return action
            blocking = False

    # ---------- 内存与收尾 ----------

    def check_memory(self, commands) -> str:
        if self.process.memory_info().rss <= self.memory_limit_bytes:
            return "continue"
        self.pause_and_save()
        self.events.put(PausedEvent(reason="memory", written_digits=self.digit_file.written_digits))
        self.emit_log("warning", "内存超过阈值，已自动暂停")
        return self.wait_while_paused(commands)

    def finish(self) -> None:
        self.append_stable_digits()
        self.digit_file.finalize()
        if self.target_digits >= 100 and pi_prefix_decimal(self.state, 100) != PI_FIRST_100:
            self.events.put(ErrorEvent(message="完成后自检失败：前 100 位与权威常数不符"))
        self.sha256_final = sha256_file(self.digit_file.path)
        self.status = "completed"
        checkpoint_module.save(
            self.checkpoint_path, self.state, stable_digits_for_terms(self.state.terms), self.snapshot_config()
        )
        self.persist_session("completed")
        self.maybe_emit_progress(force=True)
        self.events.put(DoneEvent(total_digits=self.digit_file.written_digits, sha256=self.sha256_final))
        self.emit_log("info", f"完成：{self.digit_file.written_digits:,} 位，SHA-256 {self.sha256_final}")

    def loop(self, commands, pause_after_chunks: int | None) -> None:
        self.maybe_emit_progress(force=True)
        while self.state.terms < self.target_terms:
            if self.poll_commands(commands, blocking=False) == "stop":
                return
            chunk_terms = self.next_chunk_terms()
            started = time.perf_counter()
            self.state.extend(chunk_terms, LEAF_CUTOFF_INITIAL)
            self.chunk_rates.append((chunk_terms, time.perf_counter() - started))
            self.chunks_done += 1
            self.maybe_refresh()
            self.maybe_emit_progress()
            if self.autosave_interval_s > 0 and time.perf_counter() - self.last_autosave_at >= self.autosave_interval_s:
                self.last_autosave_at = time.perf_counter()
                self.append_stable_digits()
                self.save_all(session_status="running")
                self.events.put(SavedEvent(path=str(self.session_path), written_digits=self.digit_file.written_digits))
            if pause_after_chunks is not None and self.chunks_done >= pause_after_chunks:
                self.pause_and_save()
                self.events.put(PausedEvent(reason="user", written_digits=self.digit_file.written_digits))
                return
            if self.check_memory(commands) == "stop":
                return
        self.finish()


def run_calculator(
    events,
    commands,
    output_dir,
    target_digits: int,
    refresh_interval_s: float,
    autosave_interval_s: float,
    memory_limit_bytes: int,
    resume: bool,
    pause_after_chunks: int | None = None,
) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    calculator = Calculator(
        events, output_dir, target_digits, refresh_interval_s, autosave_interval_s, memory_limit_bytes
    )
    try:
        resumed = resume and calculator.resume_from_disk()
        if not resumed:
            calculator.digit_file.open(resume_written=None)
            calculator.state = SeriesState()
        calculator.emit_log(
            "info", f"{'继续' if resumed else '开始'}计算：目标 {target_digits:,} 位，算法 {ALGORITHM_ID}"
        )
        calculator.loop(commands, pause_after_chunks)
    except Exception as error:  # noqa: BLE001 — 进程边界必须把异常上报给 GUI
        events.put(ErrorEvent(message=f"计算中断：{error}"))
        calculator.emit_log("error", f"计算中断：{error}")


def spawn_worker(
    events,
    commands,
    output_dir,
    target_digits: int,
    refresh_interval_s: float,
    autosave_interval_s: float,
    memory_limit_bytes: int,
    resume: bool,
) -> multiprocessing.Process:
    process = multiprocessing.Process(
        target=run_calculator,
        args=(
            events,
            commands,
            str(output_dir),
            target_digits,
            refresh_interval_s,
            autosave_interval_s,
            memory_limit_bytes,
            resume,
        ),
        daemon=True,
        name="pi-calculator-worker",
    )
    process.start()
    return process


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="pi_tool worker（无 GUI 模式，供测试与调试）")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--target-digits", type=int, default=10_000_000)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--pause-after-chunks", type=int, default=None)
    parser.add_argument("--refresh-interval", type=float, default=1.0)
    parser.add_argument("--autosave-interval", type=float, default=300.0)
    parser.add_argument("--memory-limit-gb", type=float, default=8.0)
    args = parser.parse_args(argv)
    events: queue.Queue = queue.Queue()
    commands: queue.Queue = queue.Queue()
    run_calculator(
        events,
        commands,
        args.output_dir,
        args.target_digits,
        args.refresh_interval,
        args.autosave_interval,
        int(args.memory_limit_gb * (1024**3)),
        args.resume,
        args.pause_after_chunks,
    )
    session_path = Path(args.output_dir) / "pi.session.json"
    if session_path.exists():
        print(session_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
