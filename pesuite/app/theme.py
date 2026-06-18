"""Visual theme: one QSS stylesheet + the status color palette.

Centralizing color here means the look can evolve in one place. The status colors
map `TaskStatus` values to the badge colors used by the Tasks and Priorities panes.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from pesuite.core import TaskStatus

# Brand + surface palette
NAVY = "#0d2440"
NAVY_LIGHT = "#1b3a63"
SURFACE = "#f3f4f7"
CARD = "#ffffff"
BORDER = "#d8dce4"
TEXT = "#1c2430"
MUTED = "#7a8494"
ACCENT = "#2f7d6e"  # teal — matches the "Launch Editor" button in the mockup

# Status -> (label, color). Used for badges/text across derived panes.
STATUS_STYLE: dict[TaskStatus, tuple[str, str]] = {
    TaskStatus.COMPLETE: ("Complete", "#3a8f4f"),
    TaskStatus.OVERDUE: ("Overdue", "#c0392b"),
    TaskStatus.IN_PROGRESS: ("Active", "#2f7d6e"),
    TaskStatus.DUE_SOON: ("Due soon", "#d98324"),
    TaskStatus.UPCOMING: ("Upcoming", "#5b6b80"),
    TaskStatus.UNSCHEDULED: ("Unscheduled", "#7a8494"),
}


def status_label(status: TaskStatus) -> str:
    return STATUS_STYLE.get(status, (status.value, MUTED))[0]


def status_color(status: TaskStatus) -> str:
    return STATUS_STYLE.get(status, (status.value, MUTED))[1]


QSS = f"""
QWidget {{
    background: {SURFACE};
    color: {TEXT};
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}}

/* Top bar */
QFrame#topBar {{
    background: {NAVY};
    border: none;
}}
QFrame#topBar QLabel {{ background: transparent; color: #eef2f8; }}
QLabel#appTitle {{ font-size: 16px; font-weight: 600; color: #ffffff; }}
QLabel#topBarLabel {{ color: #aab8cc; }}

/* Panes */
QFrame#pane {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QWidget#paneHeaderRow {{
    background: {NAVY};
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}
QWidget#paneHeaderRow QLabel {{ background: transparent; color: #ffffff; }}
QLabel#paneHeader {{
    color: #ffffff;
    font-weight: 600;
    font-size: 13px;
    padding: 8px 12px;
}}
QLabel#placeholder {{ color: {MUTED}; font-size: 14px; background: transparent; }}

/* Inputs */
QComboBox {{
    background: #ffffff;
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 10px;
    min-height: 20px;
}}
QComboBox:hover {{ border-color: {NAVY_LIGHT}; }}
QComboBox QAbstractItemView {{
    background: #ffffff;
    selection-background-color: {NAVY_LIGHT};
    selection-color: #ffffff;
}}

QPushButton {{
    background: {NAVY_LIGHT};
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
}}
QPushButton:hover {{ background: #244a7a; }}
QPushButton:disabled {{ background: #56657d; color: #c8d0db; }}
QPushButton#accent {{ background: {ACCENT}; }}
QPushButton#accent:hover {{ background: #3a8f7d; }}

/* Tree / list */
QTreeWidget, QListWidget {{
    background: #ffffff;
    border: none;
    outline: 0;
}}
QTreeWidget::item, QListWidget::item {{ padding: 4px 2px; }}
QHeaderView::section {{
    background: #eef1f6;
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 5px 8px;
    font-weight: 600;
}}
QSplitter::handle {{ background: {SURFACE}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyleSheet(QSS)
