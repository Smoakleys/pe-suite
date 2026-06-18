"""Pane base widget: a titled card with a header and a stacked body.

The body is a QStackedWidget with two pages — an empty-state placeholder and the
real content — so every pane gets consistent "nothing selected yet" handling. This
mirrors the mockup's "No tasks — open a project" / "Enable a source filter" states.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class Pane(QFrame):
    """A titled card. Subclasses add content via `set_content` and toggle states."""

    def __init__(self, title: str, header_extra: QWidget | None = None) -> None:
        super().__init__()
        self.setObjectName("pane")
        self.setFrameShape(QFrame.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header row: title + optional extra widgets (filters, buttons) on the right.
        header_row = QWidget()
        header_row.setObjectName("paneHeaderRow")
        hl = QHBoxLayout(header_row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("paneHeader")
        hl.addWidget(self._title_label)
        if header_extra is not None:
            header_extra.setStyleSheet("background: transparent;")
            hl.addStretch(1)
            hl.addWidget(header_extra)
            # keep the navy bar spanning the full width behind the extra widget
            self._title_label.setSizePolicy(self._title_label.sizePolicy().horizontalPolicy(),
                                            self._title_label.sizePolicy().verticalPolicy())
        outer.addWidget(header_row)

        # Body: placeholder page (0) + content page (1).
        self._stack = QStackedWidget()
        self._placeholder = QLabel("", alignment=Qt.AlignCenter)
        self._placeholder.setObjectName("placeholder")
        self._stack.addWidget(self._placeholder)  # index 0
        body_wrap = QWidget()
        self._body_layout = QVBoxLayout(body_wrap)
        self._body_layout.setContentsMargins(10, 10, 10, 10)
        self._stack.addWidget(body_wrap)  # index 1
        outer.addWidget(self._stack, 1)

    def set_content(self, widget: QWidget) -> None:
        self._body_layout.addWidget(widget)

    def show_placeholder(self, text: str) -> None:
        self._placeholder.setText(text)
        self._stack.setCurrentIndex(0)

    def show_content(self) -> None:
        self._stack.setCurrentIndex(1)
