"""Pane base widget: a titled card with a header, body, and a maximize control.

Every pane is a rounded "card" with:
  - a navy header showing the title, optional header widgets (filters/buttons), and a
    maximize/restore button on the far right,
  - a body that is a QStackedWidget with two pages — an empty-state placeholder and the
    real content — so every pane gets consistent "nothing selected yet" handling.

The maximize button emits `maximizeRequested`; the main window handles popping the pane
out to a full-window view and back. Subclasses never deal with maximize themselves.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# Glyphs for the maximize / restore toggle (Segoe UI Symbol renders these on Windows).
_ICON_MAXIMIZE = "⤢"   # ⤢  diagonal expand
_ICON_RESTORE = "⤡"    # ⤡  diagonal collapse


class Pane(QFrame):
    """A titled card. Subclasses add content via `set_content` and toggle states."""

    maximizeRequested = Signal()

    def __init__(self, title: str, header_extra: QWidget | None = None) -> None:
        super().__init__()
        self.title = title
        self.setObjectName("pane")
        self.setFrameShape(QFrame.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header: title | (optional extra widgets) | maximize button.
        header_row = QWidget()
        header_row.setObjectName("paneHeaderRow")
        hl = QHBoxLayout(header_row)
        hl.setContentsMargins(0, 0, 8, 0)
        hl.setSpacing(6)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("paneHeader")
        hl.addWidget(self._title_label)
        hl.addStretch(1)

        if header_extra is not None:
            header_extra.setStyleSheet("background: transparent;")
            hl.addWidget(header_extra)

        self._max_btn = QToolButton()
        self._max_btn.setObjectName("paneTool")
        self._max_btn.setText(_ICON_MAXIMIZE)
        self._max_btn.setCursor(Qt.PointingHandCursor)
        self._max_btn.setToolTip("Maximize this pane")
        self._max_btn.clicked.connect(self.maximizeRequested)
        hl.addWidget(self._max_btn)
        outer.addWidget(header_row)

        # Body: placeholder page (0) + content page (1).
        self._stack = QStackedWidget()
        self._placeholder = QLabel("", alignment=Qt.AlignCenter)
        self._placeholder.setObjectName("placeholder")
        self._stack.addWidget(self._placeholder)  # index 0
        body_wrap = QWidget()
        self._body_layout = QVBoxLayout(body_wrap)
        self._body_layout.setContentsMargins(12, 12, 12, 12)
        self._stack.addWidget(body_wrap)  # index 1
        outer.addWidget(self._stack, 1)

    def set_content(self, widget: QWidget) -> None:
        self._body_layout.addWidget(widget)

    def show_placeholder(self, text: str) -> None:
        self._placeholder.setText(text)
        self._stack.setCurrentIndex(0)

    def show_content(self) -> None:
        self._stack.setCurrentIndex(1)

    def set_maximized(self, maximized: bool) -> None:
        """Reflect the maximized state on the toggle button (called by the window)."""
        self._max_btn.setText(_ICON_RESTORE if maximized else _ICON_MAXIMIZE)
        self._max_btn.setToolTip("Restore this pane" if maximized else "Maximize this pane")
