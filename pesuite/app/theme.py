"""Visual theme: one QSS stylesheet + the status color palette.

Centralizing color here means the look can evolve in one place. The status colors
map `TaskStatus` values to the badge colors used by the Tasks and Priorities panes.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from pesuite.core import TaskStatus

# Brand + surface palette
NAVY = "#11243f"
NAVY_2 = "#1a3556"
BLUE = "#2f6fb0"
SURFACE = "#eef1f6"
SURFACE_2 = "#e6eaf2"
CARD = "#ffffff"
BORDER = "#d6dbe6"
BORDER_SOFT = "#e6eaf1"
TEXT = "#1b2230"
MUTED = "#74809a"
ACCENT = "#2f8f7d"  # teal — matches the "Launch Editor" / accent actions

# Status -> (label, color). Used for badges/text across derived panes.
STATUS_STYLE: dict[TaskStatus, tuple[str, str]] = {
    TaskStatus.COMPLETE: ("Complete", "#2f9e54"),
    TaskStatus.OVERDUE: ("Overdue", "#d2453d"),
    TaskStatus.IN_PROGRESS: ("Active", "#2f8f7d"),
    TaskStatus.DUE_SOON: ("Due soon", "#d98324"),
    TaskStatus.UPCOMING: ("Upcoming", "#5b6b88"),
    TaskStatus.UNSCHEDULED: ("Unscheduled", "#74809a"),
}


def status_label(status: TaskStatus) -> str:
    return STATUS_STYLE.get(status, (status.value, MUTED))[0]


def status_color(status: TaskStatus) -> str:
    return STATUS_STYLE.get(status, (status.value, MUTED))[1]


QSS = f"""
* {{
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}}
QWidget {{
    background: {SURFACE};
    color: {TEXT};
}}
QMainWindow, QMainWindow > QWidget {{ background: {SURFACE}; }}
QToolTip {{
    background: {NAVY};
    color: #f3f6fb;
    border: none;
    padding: 6px 9px;
    border-radius: 6px;
    font-size: 12px;
}}

/* ---- Top bar ---- */
QFrame#topBar {{
    background: {NAVY};
    border: none;
    border-bottom: 1px solid #0b1a30;
}}
QFrame#topBar QLabel {{ background: transparent; color: #d8e1ee; }}
QLabel#appTitle {{
    font-size: 17px;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: 0.3px;
}}
QLabel#topBarLabel {{ color: #93a3bd; font-size: 12px; }}

/* ---- Panes (cards) ---- */
QFrame#pane {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QWidget#paneHeaderRow {{
    background: {NAVY};
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}}
QWidget#paneHeaderRow QLabel {{ background: transparent; color: #ffffff; }}
QLabel#paneHeader {{
    color: #ffffff;
    font-weight: 600;
    font-size: 13px;
    letter-spacing: 0.2px;
    padding: 9px 14px;
}}
QLabel#placeholder {{
    color: {MUTED};
    font-size: 14px;
    background: transparent;
}}

/* Header tool buttons (maximize/restore) */
QToolButton#paneTool {{
    background: transparent;
    color: #b9c6db;
    border: none;
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 15px;
}}
QToolButton#paneTool:hover {{ background: rgba(255,255,255,0.14); color: #ffffff; }}
QToolButton#paneTool:pressed {{ background: rgba(255,255,255,0.22); }}

/* ---- Inputs ---- */
QComboBox {{
    background: #ffffff;
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 5px 12px;
    min-height: 22px;
    selection-background-color: {BLUE};
}}
QComboBox:hover {{ border-color: {BLUE}; }}
QComboBox:focus {{ border-color: {BLUE}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {MUTED};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: #ffffff;
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 4px;
    selection-background-color: {NAVY_2};
    selection-color: #ffffff;
    outline: 0;
}}

/* Top-bar combobox reads on the dark bar */
QFrame#topBar QComboBox {{
    background: #1d3454;
    color: #eef3fa;
    border: 1px solid #2c4a70;
}}
QFrame#topBar QComboBox:hover {{ border-color: {BLUE}; }}
QFrame#topBar QComboBox QAbstractItemView {{
    background: #ffffff;
    color: {TEXT};
}}

/* ---- Buttons ---- */
QPushButton {{
    background: {NAVY_2};
    color: #ffffff;
    border: none;
    border-radius: 7px;
    padding: 7px 16px;
    font-weight: 600;
}}
QPushButton:hover {{ background: #28507f; }}
QPushButton:pressed {{ background: #1c3c63; }}
QPushButton:disabled {{ background: #93a3bd; color: #e8edf5; }}
QPushButton#accent {{ background: {ACCENT}; }}
QPushButton#accent:hover {{ background: #34a08c; }}
QPushButton#accent:pressed {{ background: #287567; }}
QPushButton#ghost {{
    background: transparent;
    color: #cdd8e8;
    border: 1px solid #2c4a70;
    padding: 6px 14px;
}}
QPushButton#ghost:hover {{ background: rgba(255,255,255,0.08); color: #ffffff; }}

/* ---- Trees / lists / tables ---- */
QTreeWidget, QListWidget, QTableWidget {{
    background: #ffffff;
    border: none;
    outline: 0;
}}
QTreeWidget::item, QListWidget::item {{ padding: 4px 2px; }}
QTreeWidget::item:hover {{ background: {SURFACE}; }}
QTableWidget {{ gridline-color: {BORDER_SOFT}; }}
QTableWidget::item {{ padding: 5px 8px; }}
QTableWidget::item:selected {{ background: #e3edf8; color: {TEXT}; }}
QHeaderView::section {{
    background: #f1f4f9;
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 7px 10px;
    font-weight: 600;
    font-size: 12px;
}}

/* ---- Splitters ---- */
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 8px; }}
QSplitter::handle:vertical {{ height: 8px; }}
QSplitter::handle:hover {{ background: rgba(47,111,176,0.18); border-radius: 4px; }}

/* ---- Scrollbars ---- */
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #c2cbdb; border-radius: 5px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: #9fabc2; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #c2cbdb; border-radius: 5px; min-width: 28px; }}
QScrollBar::handle:horizontal:hover {{ background: #9fabc2; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- Status bar ---- */
QStatusBar {{ background: {SURFACE_2}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QStatusBar::item {{ border: none; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyleSheet(QSS)
