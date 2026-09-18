from __future__ import annotations

import multiprocessing
import queue
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..common import protocol
from ..common.config import Config, load_settings, sanitize, save_settings
from ..engine.worker import spawn_worker
from .export import gzip_export
from .history import remember_output, scan_sessions
from .search import SearchWorker
from .theme import apply_theme
from .widgets import DigitView, FrequencyChart, NewSessionDialog, RatePanel, SettingsDialog

CLIPBOARD_LIMIT = 1_000_000
COPY_PREFIX_DEFAULT = 100_000
BBP_COST_WARNING_POSITION = 10_000_000


class MainWindow(QMainWindow):
    def __init__(self, config: Config, settings_path: Path) -> None:
        super().__init__()
        self.config = config
        self.settings_path = settings_path
        self.commands: multiprocessing.Queue | None = None
        self.events: multiprocessing.Queue | None = None
        self.worker: multiprocessing.Process | None = None
        self.search_worker: SearchWorker | None = None
        self.state = "idle"
        self.output_dir = Path(config.output_dir)
        self.memory_limit_bytes = int(config.memory_limit_gb * (1024**3))
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll_events)
        self._timer.start()
        self._update_buttons()

    # ---------- UI 构建 ----------

    def _build_ui(self) -> None:
        self.setWindowTitle("π Calculator")
        self.resize(1120, 780)
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        header = QHBoxLayout()
        self.theme_button = QPushButton("切换主题")
        self.theme_button.clicked.connect(self._toggle_theme)
        settings_button = QPushButton("设置")
        settings_button.clicked.connect(self._open_settings)
        header.addStretch(1)
        header.addWidget(self.theme_button)
        header.addWidget(settings_button)
        root.addLayout(header)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.digits_label = QLabel("位数 0")
        self.eta_label = QLabel("ETA —（估算）")
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress, 3)
        progress_row.addWidget(self.digits_label, 3)
        progress_row.addWidget(self.eta_label, 2)
        root.addLayout(progress_row)

        self.rate_panel = RatePanel()
        self.rate_panel.unit_combo.setCurrentIndex(0 if self.config.rate_unit == "s" else 1)
        self.rate_panel.unit_combo.currentIndexChanged.connect(self._change_rate_unit)
        root.addWidget(self.rate_panel)

        self.digit_view = DigitView(self.config.view_keep_chars)
        root.addWidget(self.digit_view, 2)

        controls = QHBoxLayout()
        self.new_button = QPushButton("新计算…")
        self.continue_button = QPushButton("继续会话")
        self.pause_button = QPushButton("暂停")
        self.save_button = QPushButton("立即保存")
        self.stop_button = QPushButton("停止")
        self.copy_button = QPushButton("复制前 10 万位")
        self.export_button = QPushButton("导出 gzip…")
        self.new_button.clicked.connect(self._new_session)
        self.continue_button.clicked.connect(self._resume_session)
        self.pause_button.clicked.connect(self._pause)
        self.save_button.clicked.connect(self._save_now)
        self.stop_button.clicked.connect(self._stop)
        self.copy_button.clicked.connect(self._copy_prefix)
        self.export_button.clicked.connect(self._export)
        for widget in (
            self.new_button,
            self.continue_button,
            self.pause_button,
            self.save_button,
            self.stop_button,
            self.copy_button,
            self.export_button,
        ):
            controls.addWidget(widget)
        controls.addStretch(1)
        root.addLayout(controls)

        self.tabs = QTabWidget()

        stats_page = QWidget()
        stats_layout = QVBoxLayout(stats_page)
        self.stats_chart = FrequencyChart()
        self.stats_label = QLabel("统计随保存更新（完成后包含全部位数）")
        stats_layout.addWidget(self.stats_chart)
        stats_layout.addWidget(self.stats_label)

        search_page = QWidget()
        search_layout = QVBoxLayout(search_page)
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入要查找的数字串（空格会被忽略）")
        self.search_button = QPushButton("查找")
        self.search_button.clicked.connect(self._run_search)
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.search_button)
        self.search_results = QPlainTextEdit()
        self.search_results.setReadOnly(True)
        search_layout.addLayout(search_row)
        search_layout.addWidget(self.search_results, 1)

        bbp_page = QWidget()
        bbp_layout = QVBoxLayout(bbp_page)
        bbp_row = QHBoxLayout()
        bbp_row.addWidget(QLabel("十六进制位位置"))
        self.bbp_position = QSpinBox()
        self.bbp_position.setRange(0, 2_000_000_000)
        self.bbp_position.setValue(self.config.bbp_default_hex_position)
        self.bbp_position.setGroupSeparatorShown(True)
        self.bbp_button = QPushButton("运行 BBP 校验")
        self.bbp_button.clicked.connect(self._run_bbp)
        bbp_row.addWidget(self.bbp_position)
        bbp_row.addWidget(self.bbp_button)
        bbp_row.addStretch(1)
        self.bbp_result = QPlainTextEdit()
        self.bbp_result.setReadOnly(True)
        bbp_layout.addLayout(bbp_row)
        bbp_layout.addWidget(self.bbp_result, 1)

        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        self.rescan_button = QPushButton("重新扫描")
        self.rescan_button.clicked.connect(self._refresh_history)
        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels(["目录", "目标", "已完成", "状态", "更新", "SHA-256"])
        self.history_table.cellDoubleClicked.connect(self._resume_from_history)
        history_layout.addWidget(self.rescan_button)
        history_layout.addWidget(self.history_table, 1)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)

        self.tabs.addTab(stats_page, "统计")
        self.tabs.addTab(search_page, "搜索")
        self.tabs.addTab(bbp_page, "BBP 校验")
        self.tabs.addTab(history_page, "历史")
        self.tabs.addTab(self.log_view, "日志")
        root.addWidget(self.tabs, 1)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(f"输出目录：{self.output_dir}    SHA-256：完成后显示")
        self._refresh_history()

    # ---------- 状态机 ----------

    def _update_buttons(self) -> None:
        running = self.state == "running"
        paused = self.state == "paused"
        idle_like = self.state in {"idle", "completed", "stopped"}
        self.new_button.setEnabled(idle_like)
        self.continue_button.setEnabled(idle_like)
        self.pause_button.setEnabled(running)
        self.save_button.setEnabled(running or paused)
        self.stop_button.setEnabled(running or paused)
        self.bbp_button.setEnabled(running or paused)
        self.progress.setRange(0, 1000 if running or paused else 0)

    # ---------- worker 生命周期 ----------

    def _start_worker(self, output_dir: Path, target_digits: int, resume: bool) -> None:
        self.config.target_digits = target_digits
        self.config.output_dir = str(output_dir)
        self.events = multiprocessing.Queue()
        self.commands = multiprocessing.Queue()
        self.memory_limit_bytes = int(self.config.memory_limit_gb * (1024**3))
        self.worker = spawn_worker(
            self.events,
            self.commands,
            output_dir,
            target_digits,
            self.config.refresh_interval_s,
            self.config.autosave_interval_s,
            self.memory_limit_bytes,
            resume,
        )
        self.output_dir = output_dir
        self.state = "running"
        if not resume:
            self.digit_view.setPlainText("3.")
            self.stats_chart.set_counts([0] * 10)
        self._update_buttons()
        self.statusBar().showMessage(f"输出目录：{output_dir}")

    def _new_session(self) -> None:
        dialog = NewSessionDialog(self.config, self)
        if dialog.exec() != NewSessionDialog.DialogCode.Accepted:
            return
        target_digits, output_dir = dialog.values()
        self.config.target_digits = target_digits
        self.config.output_dir = output_dir
        sanitize(self.config)
        remember_output(self.config, output_dir)
        save_settings(self.settings_path, self.config)
        self._start_worker(Path(output_dir), target_digits, resume=False)

    def _resume_session(self) -> None:
        sessions = scan_sessions(self.config.recent_outputs or [self.config.output_dir])
        resumable = [item for item in sessions if item.status != "completed"] or sessions
        if not resumable:
            QMessageBox.information(self, "继续会话", "没有可恢复的会话，请先开始一次新计算。")
            return
        latest = resumable[0]
        self._start_worker(Path(latest.directory), latest.target_digits, resume=True)

    def _resume_from_history(self, row: int, column: int) -> None:
        directory = self.history_table.item(row, 0).text()
        target = int(self.history_table.item(row, 1).text().replace(",", "") or self.config.target_digits)
        self._start_worker(Path(directory), target, resume=True)

    def _pause(self) -> None:
        self._send(protocol.PauseCommand())

    def _save_now(self) -> None:
        self._send(protocol.SaveCommand())

    def _stop(self) -> None:
        self._send(protocol.StopCommand())

    def _send(self, command) -> None:
        if self.commands is not None:
            self.commands.put(command)

    # ---------- 事件轮询 ----------

    def _drain_events(self, limit: int = 200) -> None:
        if self.events is None:
            return
        for _ in range(limit):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return
            self._handle_event(event)

    def _poll_events(self) -> None:
        self._drain_events()
        if self.worker is not None and self.state in {"running", "paused"} and not self.worker.is_alive():
            self._append_log("error", "计算进程已退出")
            self.worker = None
            self.state = "stopped"
            self._update_buttons()
            QMessageBox.warning(
                self, "计算中断", "计算进程意外结束。进度已保存在检查点中，可点击「继续会话」恢复。"
            )

    def _handle_event(self, event) -> None:
        if isinstance(event, protocol.ProgressEvent):
            self._on_progress(event)
        elif isinstance(event, protocol.PausedEvent):
            self.state = "paused"
            self.rate_panel.set_rate(0.0, self._current_unit())
            note = "内存超限自动暂停" if event.reason == "memory" else "已暂停"
            self.statusBar().showMessage(f"{note}：已写 {event.written_digits:,} 位")
            self._update_buttons()
        elif isinstance(event, protocol.SavedEvent):
            self.statusBar().showMessage(f"已保存 {event.written_digits:,} 位 → {event.path}")
            self._refresh_history()
        elif isinstance(event, protocol.DoneEvent):
            self.state = "completed"
            self.worker = None
            self.statusBar().showMessage(f"完成 {event.total_digits:,} 位    SHA-256：{event.sha256}")
            self._update_buttons()
            self._refresh_history()
        elif isinstance(event, protocol.BbpResultEvent):
            verdict = "一致 ✔" if event.ok else "不一致 ✘"
            self.bbp_result.setPlainText(
                f"位置：十六进制第 {event.position:,} 位（{event.count} 位）\n"
                f"BBP 公式： {event.expected}\n"
                f"本引擎：   {event.got}\n"
                f"结论：{verdict}"
            )
        elif isinstance(event, protocol.ErrorEvent):
            self._append_log("error", event.message)
            QMessageBox.warning(self, "提示", event.message)
        elif isinstance(event, protocol.LogEvent):
            self._append_log(event.level, event.message)

    def _on_progress(self, event: protocol.ProgressEvent) -> None:
        if event.chunk_text:
            self.digit_view.append_digits(event.chunk_text)
        target = self.config.target_digits
        done = event.written_digits
        self.progress.setValue(int(min(1000, done / max(target, 1) * 1000)))
        self.digits_label.setText(f"位数 {done:,} / {target:,}")
        if event.eta_seconds is None:
            self.eta_label.setText("ETA —（估算）")
        else:
            minutes, seconds = divmod(int(event.eta_seconds), 60)
            hours, minutes = divmod(minutes, 60)
            if hours:
                self.eta_label.setText(f"ETA ~{hours}小时{minutes}分（估算）")
            elif minutes:
                self.eta_label.setText(f"ETA ~{minutes}分{seconds}秒（估算）")
            else:
                self.eta_label.setText(f"ETA ~{seconds}秒（估算）")
        self.rate_panel.set_rate(event.rate_digits_per_s, self._current_unit())
        self.rate_panel.set_memory(event.mem_bytes, self.memory_limit_bytes)
        self.stats_label.setText(f"统计随保存更新（当前已写 {done:,} 位）")

    def _current_unit(self) -> str:
        return self.rate_panel.unit_combo.currentData() or "s"

    def _change_rate_unit(self) -> None:
        self.config.rate_unit = self._current_unit()
        save_settings(self.settings_path, self.config)

    def _append_log(self, level: str, message: str) -> None:
        self.log_view.appendPlainText(f"[{level}] {message}")

    # ---------- 设置 / 主题 / 历史 ----------

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return
        dialog.apply_to(self.config)
        sanitize(self.config)
        save_settings(self.settings_path, self.config)
        self.memory_limit_bytes = int(self.config.memory_limit_gb * (1024**3))
        self.digit_view.keep_chars = self.config.view_keep_chars
        self._send(
            protocol.UpdateSettingsCommand(
                refresh_interval_s=self.config.refresh_interval_s,
                autosave_interval_s=float(self.config.autosave_interval_s),
                memory_limit_bytes=self.memory_limit_bytes,
            )
        )

    def _toggle_theme(self) -> None:
        self.config.theme = "light" if self.config.theme == "dark" else "dark"
        apply_theme(QApplication.instance(), self.config.theme)
        save_settings(self.settings_path, self.config)

    def _refresh_history(self) -> None:
        sessions = scan_sessions(self.config.recent_outputs or [self.config.output_dir])
        self.history_table.setRowCount(len(sessions))
        for row, item in enumerate(sessions):
            values = [
                item.directory,
                f"{item.target_digits:,}",
                f"{item.written_digits:,}",
                item.status,
                item.updated_at,
                item.sha256_prefix,
            ]
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, QTableWidgetItem(value))

    # ---------- 搜索 / BBP / 导出 / 复制 ----------

    def _run_search(self) -> None:
        needle = "".join(character for character in self.search_input.text() if character.isdigit())
        if not needle:
            return
        text_file = self.output_dir / "pi.txt"
        if not text_file.exists():
            self.search_results.setPlainText("尚无 pi.txt，先开始计算。")
            return
        if self.search_worker is not None and self.search_worker.isRunning():
            self.search_worker.cancel()
        self.search_results.setPlainText(f"正在查找 {needle} …")
        self.search_worker = SearchWorker(text_file, needle)
        self.search_worker.finished_results.connect(self._show_search_results)
        self.search_worker.failed.connect(lambda message: self.search_results.setPlainText(f"搜索失败：{message}"))
        self.search_worker.start()

    def _show_search_results(self, results: list) -> None:
        if not results:
            self.search_results.setPlainText("未找到（仅在已写入的位数范围内搜索）。")
            return
        lines = [f"命中 {len(results)} 处（小数位序号，从 1 开始）："]
        lines += [f"  第 {index:,} 位" for index, _ in results]
        self.search_results.setPlainText("\n".join(lines))

    def _run_bbp(self) -> None:
        position = self.bbp_position.value()
        if position > BBP_COST_WARNING_POSITION:
            answer = QMessageBox.question(
                self,
                "BBP 成本警告",
                "该位置非常靠后，BBP 校验可能耗时数分钟到数小时。确认继续？",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._send(protocol.BbpCheckCommand(position=position, count=self.config.bbp_default_count))

    def _copy_prefix(self) -> None:
        text_file = self.output_dir / "pi.txt"
        if not text_file.exists():
            return
        with open(text_file, "r", encoding="ascii") as handle:
            text = handle.read(COPY_PREFIX_DEFAULT + 1024)
        text = text.replace("\n", "")
        if len(text) > CLIPBOARD_LIMIT:
            text = text[:CLIPBOARD_LIMIT]
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage(f"已复制前 {len(text):,} 个字符")

    def _export(self) -> None:
        source = self.output_dir / "pi.txt"
        if not source.exists():
            QMessageBox.information(self, "导出", "尚无 pi.txt。")
            return
        target, _ = QFileDialog.getSaveFileName(self, "导出 gzip", str(source) + ".gz", "Gzip (*.gz)")
        if not target:
            return
        self.statusBar().showMessage("正在压缩导出…")
        QApplication.processEvents()
        gzip_export(source, Path(target))
        self.statusBar().showMessage(f"已导出 → {target}")

    # ---------- 关闭 ----------

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.is_alive():
            answer = QMessageBox.question(self, "退出", "计算仍在进行。停止并保存后退出？")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._send(protocol.StopCommand())
            deadline = time.monotonic() + 20.0
            while self.worker.is_alive() and time.monotonic() < deadline:
                self._drain_events(limit=1000)
                QApplication.processEvents()
                time.sleep(0.05)
            self.worker.join(timeout=2)
        if self.search_worker is not None:
            self.search_worker.cancel()
            self.search_worker.wait(2000)
        event.accept()


def run_app(argv: list[str]) -> int:
    app = QApplication(argv)
    settings_path = Path("settings.json")
    config = load_settings(settings_path)
    apply_theme(app, config.theme)
    window = MainWindow(config, settings_path)
    window.show()
    return app.exec()
