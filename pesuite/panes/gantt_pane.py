"""Gantt pane: the foundation view.

Hosts the native, read-only `GanttChart` (drawn from the schedule) plus the Launch
Editor action (wired in phase 4). Shows an empty state until a project is selected.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pesuite.app.state import AppState
from pesuite.core import LoadedProject
from .base import Pane
from .gantt_chart import (
    C_BAR_CRIT,
    C_BAR_DONE,
    C_BAR_NORMAL,
    C_SUMMARY,
    C_TODAY,
    GanttChart,
)


def _legend() -> QLabel:
    def chip(color, text):
        return (f'<span style="color:{color.name()};">&#9632;</span>'
                f'<span style="color:#5b6b80;"> {text}</span>')
    lbl = QLabel(
        "&nbsp;&nbsp;".join([
            chip(C_BAR_NORMAL, "Task"),
            chip(C_BAR_CRIT, "Critical path"),
            chip(C_BAR_DONE, "Complete"),
            chip(C_SUMMARY, "Summary"),
            chip(C_TODAY, "Today"),
        ])
        + '&nbsp;&nbsp;<span style="color:#9aa4b2;">·  Ctrl+scroll to zoom</span>'
    )
    lbl.setStyleSheet("background: transparent; padding: 4px 8px;")
    return lbl


class GanttPane(Pane):
    launchEditorRequested = Signal()

    def __init__(self, state: AppState) -> None:
        extra = QWidget()
        hl = QHBoxLayout(extra)
        hl.setContentsMargins(8, 4, 8, 4)
        self._launch = QPushButton("Launch Editor")
        self._launch.setObjectName("accent")
        self._launch.setToolTip("Open the Streamlit editor for this project (phase 4)")
        hl.addWidget(self._launch)
        super().__init__("Gantt Chart", header_extra=extra)
        self._launch.clicked.connect(self.launchEditorRequested)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        self._chart = GanttChart()
        bl.addWidget(self._chart, 1)
        bl.addWidget(_legend())
        self.set_content(body)

        state.projectChanged.connect(self.render)
        self._set_empty()

    def _set_empty(self) -> None:
        self._launch.setEnabled(False)
        self._chart.set_project(None)
        self.show_placeholder("No tasks — open a project to see the Gantt chart.")

    def render(self, loaded: LoadedProject | None) -> None:
        if loaded is None:
            self._set_empty()
            return
        self._launch.setEnabled(True)
        self._chart.set_project(loaded)
        self.show_content()
