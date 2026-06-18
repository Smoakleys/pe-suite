"""Material Tracking — a separate top-level window with its OWN project selector.

Per the design, Material Tracking lives in its own window (it hosts dense tables and a
lot of fetched/scraped data). It does not use the global selector — the user picks a
project here. Reads are cache-first from the hidden store; opening the window (and the
Refresh button) triggers a view-driven refresh of just the "material" source group.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pesuite.core import discover_projects
from pesuite.fetch_client import FetchClient

_COLUMNS = ["PO", "Item", "Status", "Qty", "ETA", "Supplier"]


class MaterialTrackingWindow(QMainWindow):
    def __init__(self, projects_dir, fetch: FetchClient, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PE Suite — Material Tracking")
        self.resize(940, 620)
        self._projects_dir = projects_dir
        self._fetch = fetch
        self._refreshed_once = False

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Project"))
        self._selector = QComboBox()
        self._selector.setMinimumWidth(300)
        bar.addWidget(self._selector)
        bar.addStretch(1)
        self._refresh_btn = QPushButton("Refresh")
        bar.addWidget(self._refresh_btn)
        layout.addLayout(bar)

        self._stack = QStackedWidget()
        self._placeholder = QLabel("No material records yet — click Refresh to fetch.",
                                   alignment=Qt.AlignCenter)
        self._placeholder.setObjectName("placeholder")
        self._stack.addWidget(self._placeholder)  # 0

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._stack.addWidget(self._table)  # 1
        layout.addWidget(self._stack, 1)

        self.setCentralWidget(central)

        self._selector.currentIndexChanged.connect(self._on_project_changed)
        self._refresh_btn.clicked.connect(self._do_refresh)
        self._fetch.refreshStarted.connect(self._on_refresh_started)
        self._fetch.refreshed.connect(self._on_refreshed)

        self.refresh_projects()
        self._reload()

    # -- projects --------------------------------------------------------
    def refresh_projects(self) -> None:
        current = self._selector.currentData()
        self._selector.blockSignals(True)
        self._selector.clear()
        for ref in discover_projects(self._projects_dir):
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
            self._stack.setCurrentIndex(0)
            return
        for rec in records:
            data = rec.get("data", {}) or {}
            values = [
                str(data.get("po", rec.get("rec_key", ""))),
                rec.get("title", ""),
                str(data.get("status", "")),
                str(data.get("qty", "")),
                str(data.get("eta", "")),
                str(data.get("supplier", "")),
            ]
            row = self._table.rowCount()
            self._table.insertRow(row)
            for col, val in enumerate(values):
                self._table.setItem(row, col, QTableWidgetItem(val))
        self._stack.setCurrentIndex(1)
