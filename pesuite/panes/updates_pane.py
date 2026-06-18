"""Updates pane: the cross-source change feed, with its OWN filters.

Independent of the global selector — its project + source dropdowns filter the feed
without moving the Gantt/Tasks/Priorities selection. Reads are cache-first (instant from
the store); a view-driven refresh runs once when the pane first appears, and the Refresh
button forces one on demand. Each change event renders as a card with a new/updated/
removed badge.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pesuite.core import ProjectRef
from pesuite.fetch_client import FetchClient
from fetch_service.models import UpdateRow
from .base import Pane

_CHANGE = {
    "new": ("New", "#3a8f4f"),
    "changed": ("Updated", "#d98324"),
    "removed": ("Removed", "#c0392b"),
}


def _rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


class _UpdateCard(QFrame):
    def __init__(self, up: UpdateRow, source_name: str) -> None:
        super().__init__()
        label, color = _CHANGE.get(up.change_type, (up.change_type, "#5b6b80"))
        self.setObjectName("updCard")
        self.setStyleSheet(
            f"""
            QFrame#updCard {{
                background: #ffffff;
                border: 1px solid #e2e6ee;
                border-left: 4px solid {color};
                border-radius: 8px;
            }}
            QFrame#updCard QLabel {{ background: transparent; }}
            """
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(3)

        top = QHBoxLayout()
        badge = QLabel(label)
        badge.setStyleSheet(
            f"background: {_rgba(color, 0.15)}; color: {color}; border-radius: 8px;"
            f"padding: 1px 8px; font-size: 10px; font-weight: 700;"
        )
        top.addWidget(badge, 0)
        title = QLabel(up.title)
        title.setStyleSheet("font-weight: 600; color: #1c2430;")
        title.setWordWrap(True)
        top.addWidget(title, 1)
        outer.addLayout(top)

        if up.summary:
            body = QLabel(up.summary)
            body.setStyleSheet("color: #5b6b80; font-size: 12px;")
            body.setWordWrap(True)
            outer.addWidget(body)

        when = up.at.strftime("%b %d, %H:%M") if up.at else ""
        meta = QLabel(f"{source_name}  ·  {when}".strip(" ·"))
        meta.setStyleSheet("color: #9aa4b2; font-size: 11px;")
        outer.addWidget(meta)


class UpdatesPane(Pane):
    def __init__(self, fetch: FetchClient) -> None:
        self._fetch = fetch
        self._refreshed_once = False

        extra = QWidget()
        hl = QHBoxLayout(extra)
        hl.setContentsMargins(8, 4, 8, 4)
        hl.setSpacing(6)
        self._project_filter = QComboBox()
        self._project_filter.addItem("All projects", userData=None)
        self._source_filter = QComboBox()
        self._source_filter.addItem("All sources", userData=None)
        self._refresh_btn = QPushButton("Refresh")
        hl.addWidget(QLabel("Project"))
        hl.addWidget(self._project_filter)
        hl.addWidget(QLabel("Source"))
        hl.addWidget(self._source_filter)
        hl.addWidget(self._refresh_btn)

        super().__init__("Updates", header_extra=extra)

        self._list = QListWidget()
        self._list.setSpacing(5)
        self._list.setSelectionMode(QListWidget.NoSelection)
        self._list.setFocusPolicy(Qt.NoFocus)
        self.set_content(self._list)
        self.show_placeholder("No updates yet — click Refresh to fetch.")

        self._project_filter.currentIndexChanged.connect(self._reload)
        self._source_filter.currentIndexChanged.connect(self._reload)
        self._refresh_btn.clicked.connect(self._do_refresh)
        fetch.refreshStarted.connect(self._on_refresh_started)
        fetch.refreshed.connect(self._on_refreshed)

        self._reload()

    # -- public ----------------------------------------------------------
    def set_projects(self, refs: list[ProjectRef]) -> None:
        current = self._project_filter.currentData()
        self._project_filter.blockSignals(True)
        self._project_filter.clear()
        self._project_filter.addItem("All projects", userData=None)
        for ref in refs:
            self._project_filter.addItem(ref.name, userData=ref.id)
        idx = self._project_filter.findData(current)
        self._project_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self._project_filter.blockSignals(False)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._refreshed_once:
            self._refreshed_once = True
            self._do_refresh()

    # -- internals -------------------------------------------------------
    def _do_refresh(self) -> None:
        pid = self._project_filter.currentData()
        self._fetch.refresh_group("updates", project_id=pid, force=True)

    def _on_refresh_started(self, group: str) -> None:
        if group == "updates":
            self._refresh_btn.setEnabled(False)
            self._refresh_btn.setText("Refreshing…")

    def _on_refreshed(self, group: str, ok: bool) -> None:
        if group != "updates":
            return
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("Refresh")
        self._reload()

    def _sync_source_filter(self) -> None:
        current = self._source_filter.currentData()
        self._source_filter.blockSignals(True)
        self._source_filter.clear()
        self._source_filter.addItem("All sources", userData=None)
        for sid, name in self._fetch.source_names().items():
            self._source_filter.addItem(name, userData=sid)
        idx = self._source_filter.findData(current)
        self._source_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self._source_filter.blockSignals(False)

    def _reload(self) -> None:
        self._sync_source_filter()
        names = self._fetch.source_names()
        pid = self._project_filter.currentData()
        sid = self._source_filter.currentData()
        rows = self._fetch.updates(project_id=pid, source_id=sid)

        self._list.clear()
        if not rows:
            self.show_placeholder("No updates match these filters.")
            return
        for up in rows:
            card = _UpdateCard(up, names.get(up.source_id, up.source_id))
            li = QListWidgetItem(self._list)
            li.setSizeHint(QSize(0, card.sizeHint().height()))
            self._list.addItem(li)
            self._list.setItemWidget(li, card)
        self.show_content()
