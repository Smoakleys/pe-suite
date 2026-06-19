"""Material Tracking pane: a project picker that launches per-project windows.

Lives below Priorities in the right column. It is NOT a data table — it shows one small
box per project (from the same project JSON the derived panes use). Clicking a box opens
Material Tracking for that project in its own window, where the fetched material data is
shown. Independent of the global selector.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from pesuite.core import ProjectRef
from .base import Pane

_COLUMNS = 2  # project boxes per row


class _ProjectBox(QToolButton):
    """A small clickable card showing a project name."""

    def __init__(self, ref: ProjectRef) -> None:
        super().__init__()
        self.ref = ref
        self.setText(ref.name)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(
            """
            QToolButton {
                background: #f4f7fb;
                border: 1px solid #d6dbe6;
                border-radius: 10px;
                padding: 12px 14px;
                font-size: 13px;
                font-weight: 600;
                color: #1b2230;
                text-align: left;
            }
            QToolButton:hover { background: #eaf1fb; border-color: #2f6fb0; }
            QToolButton:pressed { background: #dbe7f6; }
            """
        )


class MaterialPane(Pane):
    # Emitted (project_id, project_name) when a project box is clicked.
    openRequested = Signal(str, str)

    def __init__(self) -> None:
        super().__init__("Material Tracking")
        self._refs: list[ProjectRef] = []

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(2, 2, 2, 2)
        self._grid.setSpacing(10)
        self._grid.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._grid_host)
        self.set_content(scroll)

        self.show_placeholder("No projects found.")

    def set_projects(self, refs: list[ProjectRef]) -> None:
        self._refs = refs
        # clear existing boxes
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        if not refs:
            self.show_placeholder("No projects found.")
            return

        hint = QLabel("Choose a project to open its Material Tracking window:")
        hint.setStyleSheet("color: #74809a; font-size: 12px;")
        hint.setWordWrap(True)
        self._grid.addWidget(hint, 0, 0, 1, _COLUMNS)

        for i, ref in enumerate(refs):
            box = _ProjectBox(ref)
            box.clicked.connect(lambda _=False, r=ref: self.openRequested.emit(r.id, r.name))
            row = 1 + i // _COLUMNS
            col = i % _COLUMNS
            self._grid.addWidget(box, row, col)

        self.show_content()
