from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..common.config import TARGET_DIGITS_MAX, TARGET_DIGITS_MIN, Config
from .theme import DIGIT_FONT_FAMILIES, DIGIT_FONT_POINT_SIZE

VIEW_MAX_INSERT = 2_000_000


class DigitView(QPlainTextEdit):
    def __init__(self, keep_chars: int = 200_000) -> None:
        super().__init__()
        self.keep_chars = keep_chars
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont()
        font.setFamilies(DIGIT_FONT_FAMILIES)
        font.setPointSize(DIGIT_FONT_POINT_SIZE)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setPlaceholderText("等待开始计算…")
        self.setPlainText("3.")

    def append_digits(self, chunk: str) -> None:
        if not chunk:
            return
        if len(chunk) >= self.keep_chars:
            self.setPlainText(chunk[-self.keep_chars :])
        elif len(chunk) > VIEW_MAX_INSERT:
            merged = (self.toPlainText() + chunk)[-self.keep_chars :]
            self.setPlainText(merged)
        else:
            self.moveCursor(QTextCursor.MoveOperation.End)
            self.insertPlainText(chunk)
            overflow = self.document().characterCount() - 1 - self.keep_chars
            if overflow > 0:
                cursor = self.textCursor()
                cursor.setPosition(0)
                cursor.setPosition(overflow, QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class RatePanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.rate_label = QLabel("0 位/秒")
        self.rate_label.setObjectName("rateLabel")
        self.unit_combo = QComboBox()
        self.unit_combo.addItem("位/秒", "s")
        self.unit_combo.addItem("位/分", "m")
        self.memory_bar = QProgressBar()
        self.memory_bar.setRange(0, 100)
        self.memory_bar.setTextVisible(False)
        self.memory_bar.setFixedWidth(220)
        self.memory_label = QLabel("内存 0.00 GB / 0.0 GB")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.rate_label)
        layout.addWidget(self.unit_combo)
        layout.addStretch(1)
        layout.addWidget(self.memory_label)
        layout.addWidget(self.memory_bar)

    def set_rate(self, digits_per_second: float, unit: str) -> None:
        value = digits_per_second * 60 if unit == "m" else digits_per_second
        suffix = "位/分" if unit == "m" else "位/秒"
        self.rate_label.setText(f"{value:,.0f} {suffix}")

    def set_memory(self, used_bytes: int, limit_bytes: int) -> None:
        used_gb = used_bytes / (1024**3)
        limit_gb = limit_bytes / (1024**3)
        percent = int(min(100, used_gb / limit_gb * 100)) if limit_gb > 0 else 0
        self.memory_label.setText(f"内存 {used_gb:.2f} GB / {limit_gb:.1f} GB")
        self.memory_bar.setValue(percent)
        state = "danger" if percent >= 95 else "warn" if percent >= 80 else "ok"
        self.memory_bar.setProperty("state", state)
        self.memory_bar.style().unpolish(self.memory_bar)
        self.memory_bar.style().polish(self.memory_bar)


class FrequencyChart(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.counts = [0] * 10
        self.setMinimumHeight(170)

    def set_counts(self, counts: list[int]) -> None:
        self.counts = list(counts)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        height = self.height()
        maximum = max(self.counts) if any(self.counts) else 1
        slot = width / 10
        painter.setPen(self.palette().color(self.foregroundRole()))
        for index, count in enumerate(self.counts):
            bar_height = int((height - 40) * count / maximum)
            painter.fillRect(
                int(index * slot + slot * 0.15),
                height - 26 - bar_height,
                int(slot * 0.7),
                bar_height,
                QColor("#4f8cff"),
            )
            text = f"{index}\n{count:,}" if count else str(index)
            painter.drawText(int(index * slot), height - 22, int(slot), 20, Qt.AlignmentFlag.AlignCenter, text)


class NewSessionDialog(QDialog):
    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新计算")
        self.setMinimumWidth(520)
        self.target_spin = QSpinBox()
        self.target_spin.setRange(TARGET_DIGITS_MIN, TARGET_DIGITS_MAX)
        self.target_spin.setValue(config.target_digits)
        self.target_spin.setGroupSeparatorShown(True)
        self.output_edit = QLineEdit(config.output_dir)
        browse_button = QPushButton("浏览…")
        browse_button.clicked.connect(self._browse)
        self.estimate_label = QLabel()
        self.estimate_label.setWordWrap(True)
        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("目标位数"))
        target_row.addWidget(self.target_spin, 1)
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("输出目录"))
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(browse_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(target_row)
        layout.addLayout(output_row)
        layout.addWidget(self.estimate_label)
        layout.addWidget(buttons)
        self.target_spin.valueChanged.connect(self._update_estimate)
        self._update_estimate()

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_edit.text() or ".")
        if chosen:
            self.output_edit.setText(chosen)

    def _update_estimate(self) -> None:
        digits = self.target_spin.value()
        text_mb = digits / (1024 * 1024)
        checkpoint_mb = digits * 2.5 / (1024 * 1024)
        memory_gb = digits * 2.5 / (1024**3)
        self.estimate_label.setText(
            f"估算：pi.txt ≈ {text_mb:,.1f} MB ｜ 检查点 ≈ {checkpoint_mb:,.1f} MB ｜ 内存峰值 ≈ {memory_gb:,.2f} GB"
        )

    def values(self) -> tuple[int, str]:
        return self.target_spin.value(), (self.output_edit.text().strip() or "output")


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.refresh_spin = QDoubleSpinBox()
        self.refresh_spin.setRange(0.1, 60.0)
        self.refresh_spin.setDecimals(1)
        self.refresh_spin.setSuffix(" 秒")
        self.refresh_spin.setValue(config.refresh_interval_s)
        self.autosave_spin = QSpinBox()
        self.autosave_spin.setRange(10, 3600)
        self.autosave_spin.setSuffix(" 秒")
        self.autosave_spin.setValue(config.autosave_interval_s)
        self.memory_spin = QDoubleSpinBox()
        self.memory_spin.setRange(0.5, 128.0)
        self.memory_spin.setDecimals(1)
        self.memory_spin.setSuffix(" GB")
        self.memory_spin.setValue(config.memory_limit_gb)
        self.keep_spin = QSpinBox()
        self.keep_spin.setRange(10_000, 5_000_000)
        self.keep_spin.setSingleStep(10_000)
        self.keep_spin.setValue(config.view_keep_chars)
        form = QVBoxLayout(self)
        for label, widget in (
            ("刷新间隔", self.refresh_spin),
            ("自动保存间隔", self.autosave_spin),
            ("内存阈值", self.memory_spin),
            ("显示保留字符数", self.keep_spin),
        ):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(widget, 1)
            form.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addWidget(buttons)

    def apply_to(self, config: Config) -> Config:
        config.refresh_interval_s = self.refresh_spin.value()
        config.autosave_interval_s = self.autosave_spin.value()
        config.memory_limit_gb = self.memory_spin.value()
        config.view_keep_chars = self.keep_spin.value()
        return config
