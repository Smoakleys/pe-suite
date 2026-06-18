"""Priorities pane: the critical-path long pole, ranked as cards.

Driven by the global selector. Each actionable, incomplete critical task is rendered as
a card — rank badge, name, urgency subtext, and a status pill — in the order it needs to
happen. This is the "what do I act on next" view.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pesuite.app.state import AppState
from pesuite.app.theme import status_color, status_label
from pesuite.core import LoadedProject, PriorityItem, priorities
from .base import Pane


def _rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def _fmt(d) -> str:
    return d.isoformat() if d else "—"


class _PriorityCard(QFrame):
    def __init__(self, item: PriorityItem) -> None:
        super().__init__()
        color = status_color(item.status)
        self.setObjectName("prioCard")
        self.setStyleSheet(
            f"""
            QFrame#prioCard {{
                background: {_rgba(color, 0.07)};
                border: 1px solid {_rgba(color, 0.22)};
                border-left: 4px solid {color};
                border-radius: 8px;
            }}
            QFrame#prioCard QLabel {{ background: transparent; }}
            """
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)

        badge = QLabel(str(item.rank))
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(26, 26)
        badge.setStyleSheet(
            f"background: {color}; color: white; font-weight: 700;"
            f"border-radius: 13px;"
        )
        row.addWidget(badge, 0, Qt.AlignTop)

        mid = QVBoxLayout()
        mid.setSpacing(2)
        name = QLabel(item.name)
        name.setStyleSheet("font-weight: 600; font-size: 13px; color: #1c2430;")
        name.setWordWrap(True)
        mid.addWidget(name)

        if item.days_overdue:
            sub = f"{item.days_overdue} day{'s' if item.days_overdue != 1 else ''} overdue"
        elif item.days_until_start:
            sub = f"starts in {item.days_until_start} day{'s' if item.days_until_start != 1 else ''}"
        else:
            sub = f"due {_fmt(item.finish)}"
        sub_lbl = QLabel(f"{_fmt(item.start)} → {_fmt(item.finish)}  ·  {sub}")
        sub_lbl.setStyleSheet("color: #7a8494; font-size: 11px;")
        mid.addWidget(sub_lbl)
        row.addLayout(mid, 1)

        pill = QLabel(status_label(item.status))
        pill.setAlignment(Qt.AlignCenter)
        pill.setStyleSheet(
            f"background: {_rgba(color, 0.16)}; color: {color};"
            f"border-radius: 9px; padding: 2px 10px; font-size: 11px; font-weight: 600;"
        )
        row.addWidget(pill, 0, Qt.AlignTop)


class PrioritiesPane(Pane):
    def __init__(self, state: AppState) -> None:
        super().__init__("Priorities")
        self._list = QListWidget()
        self._list.setSpacing(5)
        self._list.setSelectionMode(QListWidget.NoSelection)
        self._list.setFocusPolicy(Qt.NoFocus)
        self._list.setStyleSheet("QListWidget::item { padding: 0; }")
        self.set_content(self._list)

        state.projectChanged.connect(self.render)
        self.show_placeholder("No project selected.")

    def render(self, loaded: LoadedProject | None) -> None:
        self._list.clear()
        if loaded is None:
            self.show_placeholder("No project selected.")
            return

        items = priorities(loaded)
        if not items:
            self.show_placeholder("No open critical-path tasks. 🎉")
            return

        for it in items:
            card = _PriorityCard(it)
            li = QListWidgetItem(self._list)
            li.setSizeHint(QSize(0, card.sizeHint().height()))
            self._list.addItem(li)
            self._list.setItemWidget(li, card)

        self.show_content()
