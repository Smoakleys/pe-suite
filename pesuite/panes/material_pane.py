"""Material Tracking pane: fetched material/PO status, with its OWN project selector.

Lives below Priorities in the right column. Independent of the global selector — the
user picks a project here. Reads are cache-first from the hidden store; the pane runs a
view-driven refresh of just the "material" source group when it first appears, and the
Refresh button forces one on demand.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from pesuite.core import ProjectRef
from pesuite.fetch_client import FetchClient
from .base import Pane

_COLUMNS = ["PO", "Item", "Status", "Qty", "ETA", "Supplier"]
_STATUS_COLOR = {
    "Delivered": "#2f9e54",
    "In Transit": "#2f8f7d",
    "Ordered": "#d98324",
    "Delayed": "#d2453d",
}


class MaterialPane(Pane):
    def __init__(self, fetch: FetchClient) -> None:
        self._fetch = fetch
        self._refreshed_once = False

        extra = QWidget()
        hl = QHBoxLayout(extra)
        hl.setContentsMargins(0, 4, 0, 4)
        hl.setSpacing(6)
        self._selector = QComboBox()
        self._selector.setMinimumWidth(180)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setObjectName("ghost")
        hl.addWidget(QLabel("Project"))
        hl.addWidget(self._selector)
        hl.addWidget(self._refresh_btn)

        super().__init__("Material Tracking", header_extra=extra)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.set_content(self._table)
        self.show_placeholder("No material records yet — click Refresh to fetch.")

        self._selector.currentIndexChanged.connect(self._on_project_changed)
        self._refresh_btn.clicked.connect(self._do_refresh)
        self._fetch.refreshStarted.connect(self._on_refresh_started)
        self._fetch.refreshed.connect(self._on_refreshed)

        self._reload()

    # -- public ----------------------------------------------------------
    def set_projects(self, refs: list[ProjectRef]) -> None:
        current = self._selector.currentData()
        self._selector.blockSignals(True)
        self._selector.clear()
        for ref in refs:
            self._selector.addItem(ref.name, userData=ref.id)
        idx = self._selector.findData(current)
        if idx >= 0:
            self._selector.setCurrentIndex(idx)
        self._selector.blockSignals(False)

    def _current_project_id(self) -> str | None:
        return self._selector.currentData()

    # -- lifecycle / refresh --------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._refreshed_once:
            self._refreshed_once = True
            self._do_refresh()

    def _on_project_changed(self, _i: int) -> None:
        self._reload()
        self._do_refresh()

    def _do_refresh(self) -> None:
        self._fetch.refresh_group("material", project_id=self._current_project_id(), force=True)

    def _on_refresh_started(self, group: str) -> None:
        if group == "material":
            self._refresh_btn.setEnabled(False)
            self._refresh_btn.setText("Refreshing…")

    def _on_refreshed(self, group: str, ok: bool) -> None:
        if group != "material":
            return
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("Refresh")
        self._reload()

    def _reload(self) -> None:
        records = self._fetch.materials(project_id=self._current_project_id())
        self._table.setRowCount(0)
        if not records:
            self.show_placeholder("No material records for this project yet.")
            return
        for rec in records:
            data = rec.get("data", {}) or {}
            status = str(data.get("status", ""))
            values = [
                str(data.get("po", rec.get("rec_key", ""))),
                rec.get("title", ""),
                status,
                str(data.get("qty", "")),
                str(data.get("eta", "")),
                str(data.get("supplier", "")),
            ]
            row = self._table.rowCount()
            self._table.insertRow(row)
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col == 2 and status in _STATUS_COLOR:
                    from PySide6.QtGui import QColor
                    item.setForeground(QColor(_STATUS_COLOR[status]))
                self._table.setItem(row, col, item)
        self.show_content()
