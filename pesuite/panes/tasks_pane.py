"""Tasks pane: the selected project's task hierarchy.

Driven by the global selector via AppState. Renders the `task_rows` view as a tree,
preserving parent/child nesting and declaration order, with a status badge per task.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from pesuite.app.state import AppState
from pesuite.app.theme import status_color, status_label
from pesuite.core import LoadedProject, TaskStatus, task_rows
from .base import Pane


def _fmt(d) -> str:
    return d.isoformat() if d else "—"


class TasksPane(Pane):
    def __init__(self, state: AppState) -> None:
        super().__init__("Tasks")
        self._tree = QTreeWidget()
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(["Task", "Status", "Start", "Finish"])
        self._tree.setRootIsDecorated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.header().setStretchLastSection(False)
        self.set_content(self._tree)

        state.projectChanged.connect(self.render)
        self.show_placeholder("No project selected.")

    def render(self, loaded: LoadedProject | None) -> None:
        self._tree.clear()
        if loaded is None:
            self.show_placeholder("No project selected.")
            return

        items: dict[str, QTreeWidgetItem] = {}
        for row in task_rows(loaded):
            item = QTreeWidgetItem([
                row.name,
                status_label(row.status),
                _fmt(row.start),
                _fmt(row.finish),
            ])
            item.setForeground(1, QBrush(QColor(status_color(row.status))))
            if row.is_parent:
                font = QFont()
                font.setBold(True)
                item.setFont(0, font)
            if row.is_critical:
                item.setToolTip(0, "On the critical path")

            parent_item = items.get(row.parent_id) if row.parent_id else None
            if parent_item is not None:
                parent_item.addChild(item)
            else:
                self._tree.addTopLevelItem(item)
            items[row.id] = item

        self._tree.expandAll()
        for col in (1, 2, 3):
            self._tree.resizeColumnToContents(col)
        self._tree.setColumnWidth(0, 240)
        self.show_content()
