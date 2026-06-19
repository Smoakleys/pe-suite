"""Material Tracking — a separate window opened for ONE project.

Launched by clicking a project box in the Material Tracking pane. It shows that
project's material/PO records from the hidden fetch store (cache-first) and refreshes the
"material" source group for that project on open and on demand. Until a real material
source is connected, it shows an honest empty state — never fabricated data.

It is a real top-level window, so it is independently movable, resizable, and
full-screenable by the OS.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
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

from PySide6.QtGui import QColor

from pesuite.fetch_client import FetchClient

_COLUMNS = ["PO", "Item", "Status", "Qty", "ETA", "Supplier"]
_STATUS_COLOR = {
    "Delivered": "#2f9e54",
    "In Transit": "#2f8f7d",
    "Ordered": "#d98324",
    "Delayed": "#d2453d",
}


class MaterialTrackingWindow(QMainWindow):
    closed = Signal(str)  # emits project_id when the window closes

    def __init__(self, project_id: str, project_name: str, fetch: FetchClient,
                 parent=None) -> None:
        super().__init__(parent)
        self.project_id = project_id
        self._fetch = fetch
        self.setWindowTitle(f"Material Tracking — {project_name}")
        self.resize(960, 620)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        bar = QHBoxLayout()
        heading = QLabel(project_name)
        heading.setStyleSheet("font-size: 16px; font-weight: 700; color: #11243f;")
        bar.addWidget(heading)
        bar.addStretch(1)
        self._refresh_btn = QPushButton("Refresh")
        bar.addWidget(self._refresh_btn)
        layout.addLayout(bar)

        self._stack = QStackedWidget()
        self._placeholder = QLabel(
            "No material data for this project yet.\n\n"
            "Connect a material source to populate this view "
            "(see ARCHITECTURE.md → Add a new fetched source).",
            alignment=Qt.AlignCenter,
        )
        self._placeholder.setObjectName("placeholder")
        self._stack.addWidget(self._placeholder)  # 0

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._stack.addWidget(self._table)  # 1
        layout.addWidget(self._stack, 1)

        self.setCentralWidget(central)

        self._refresh_btn.clicked.connect(self._do_refresh)
        self._fetch.refreshStarted.connect(self._on_refresh_started)
        self._fetch.refreshed.connect(self._on_refreshed)

        self._reload()
        self._do_refresh()

    # -- refresh ---------------------------------------------------------
    def _do_refresh(self) -> None:
        self._fetch.refresh_group("material", project_id=self.project_id, force=True)

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
        records = self._fetch.materials(project_id=self.project_id)
        self._table.setRowCount(0)
        if not records:
            self._stack.setCurrentIndex(0)
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
                    item.setForeground(QColor(_STATUS_COLOR[status]))
                self._table.setItem(row, col, item)
        self._stack.setCurrentIndex(1)

    def closeEvent(self, event) -> None:
        self.closed.emit(self.project_id)
        super().closeEvent(event)
