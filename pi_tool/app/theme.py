from __future__ import annotations

from PySide6.QtWidgets import QApplication

DIGIT_FONT_FAMILIES = ["JetBrains Mono", "Consolas", "Menlo", "Monospace"]
DIGIT_FONT_POINT_SIZE = 13

DARK_QSS = """
QWidget { background-color: #1e1f22; color: #e6e6e6; font-size: 13px; }
QMainWindow, QDialog { background-color: #1e1f22; }
QPushButton { background-color: #3a3d42; border: none; border-radius: 8px; padding: 8px 16px; }
QPushButton:hover:!disabled { background-color: #4a4e55; }
QPushButton:disabled { color: #77787b; background-color: #2b2d31; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTableWidget {
    background-color: #2b2d31; border: 1px solid #3a3d42; border-radius: 6px; padding: 4px;
}
QProgressBar { background-color: #2b2d31; border-radius: 6px; text-align: center; }
QProgressBar::chunk { background-color: #4f8cff; border-radius: 6px; }
QProgressBar[state="warn"]::chunk { background-color: #e0a63c; }
QProgressBar[state="danger"]::chunk { background-color: #d9534f; }
QTabWidget::pane { border: 1px solid #3a3d42; border-radius: 8px; }
QTabBar::tab { background: #2b2d31; padding: 6px 14px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background: #4f8cff; color: #ffffff; }
QHeaderView::section { background-color: #2b2d31; border: none; padding: 4px; }
QStatusBar { background-color: #2b2d31; }
#rateLabel { font-size: 22px; font-weight: 600; color: #7fb2ff; }
"""

LIGHT_QSS = """
QWidget { background-color: #f5f6f8; color: #1f2328; font-size: 13px; }
QMainWindow, QDialog { background-color: #f5f6f8; }
QPushButton { background-color: #e3e6ea; border: none; border-radius: 8px; padding: 8px 16px; }
QPushButton:hover:!disabled { background-color: #d5dae0; }
QPushButton:disabled { color: #9aa0a6; background-color: #eceef1; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTableWidget {
    background-color: #ffffff; border: 1px solid #d0d4da; border-radius: 6px; padding: 4px;
}
QProgressBar { background-color: #e3e6ea; border-radius: 6px; text-align: center; }
QProgressBar::chunk { background-color: #3574e0; border-radius: 6px; }
QProgressBar[state="warn"]::chunk { background-color: #d08700; }
QProgressBar[state="danger"]::chunk { background-color: #c0392b; }
QTabWidget::pane { border: 1px solid #d0d4da; border-radius: 8px; }
QTabBar::tab { background: #e3e6ea; padding: 6px 14px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background: #3574e0; color: #ffffff; }
QHeaderView::section { background-color: #eceef1; border: none; padding: 4px; }
QStatusBar { background-color: #eceef1; }
#rateLabel { font-size: 22px; font-weight: 600; color: #2456b8; }
"""


def apply_theme(app: QApplication, name: str) -> None:
    app.setStyleSheet(LIGHT_QSS if name == "light" else DARK_QSS)
