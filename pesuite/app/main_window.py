"""The PE Suite main window: top bar, four-pane layout, global selector, file-watch.

Layout mirrors the mockup:

    +-----------------------------------------------------------+
    |  PE Suite        Project [ ... v]   [Material Tracking]   |  top bar
    +----------------------------+------------------------------+
    |  Gantt Chart               |  Priorities                 |
    +----------------------------+------------------------------+
    |  Tasks                     |  Updates                    |
    +----------------------------+------------------------------+

The global selector lives in the TOP BAR (app-level), not in any pane, and drives
Gantt + Tasks + Priorities through AppState. Updates and Material Tracking keep their
own independent filters. A QFileSystemWatcher auto-reloads on edits to projects/.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QFileSystemWatcher

from pesuite import config
from pesuite.app.editor_launcher import StreamlitEditor
from pesuite.app.material_window import MaterialTrackingWindow
from pesuite.app.state import AppState
from pesuite.core import discover_projects
from pesuite.fetch_client import FetchClient
from pesuite.panes import GanttPane, PrioritiesPane, TasksPane, UpdatesPane

_NO_SELECTION = "— Select project —"


class MainWindow(QMainWindow):
    def __init__(self, state: AppState | None = None, projects_dir: Path | None = None) -> None:
        super().__init__()
        self.state = state or AppState()
        self._projects_dir = Path(projects_dir or config.projects_dir())
        self._material_window: MaterialTrackingWindow | None = None

        # Services the panes depend on must exist before the panes are built.
        self._fetch = FetchClient(parent=self)
        self._editor = StreamlitEditor(config.streamlit_script(), parent=self)
        self._editor.statusChanged.connect(lambda m: self.statusBar().showMessage(m, 6000))
        self._editor.failed.connect(lambda m: self.statusBar().showMessage(m, 8000))

        self.setWindowTitle("PE Suite")
        self.resize(1400, 900)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_top_bar())
        root_layout.addWidget(self._build_panes(), 1)
        self.setCentralWidget(root)

        self.state.projectChanged.connect(self._on_project_changed)
        self.state.loadFailed.connect(self._on_load_failed)

        self._setup_watcher()
        self.refresh_project_list()

    # -- top bar ----------------------------------------------------------
    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setFixedHeight(52)
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(10)

        title = QLabel("PE Suite")
        title.setObjectName("appTitle")
        hl.addWidget(title)
        hl.addSpacing(24)

        lbl = QLabel("Project")
        lbl.setObjectName("topBarLabel")
        hl.addWidget(lbl)

        self.selector = QComboBox()
        self.selector.setMinimumWidth(320)
        self.selector.currentIndexChanged.connect(self._on_selector_changed)
        hl.addWidget(self.selector)

        hl.addStretch(1)

        self.material_button = QPushButton("Material Tracking  ↗")
        self.material_button.clicked.connect(self.open_material_tracking)
        hl.addWidget(self.material_button)
        return bar

    # -- panes ------------------------------------------------------------
    def _build_panes(self) -> QWidget:
        self.gantt_pane = GanttPane(self.state)
        self.priorities_pane = PrioritiesPane(self.state)
        self.tasks_pane = TasksPane(self.state)
        self.updates_pane = UpdatesPane(self._fetch)

        self.gantt_pane.launchEditorRequested.connect(self._on_launch_editor)

        top_split = QSplitter(Qt.Horizontal)
        top_split.addWidget(self.gantt_pane)
        top_split.addWidget(self.priorities_pane)
        top_split.setSizes([900, 500])

        bottom_split = QSplitter(Qt.Horizontal)
        bottom_split.addWidget(self.tasks_pane)
        bottom_split.addWidget(self.updates_pane)
        bottom_split.setSizes([700, 700])

        v_split = QSplitter(Qt.Vertical)
        v_split.addWidget(top_split)
        v_split.addWidget(bottom_split)
        v_split.setSizes([560, 320])

        container = QWidget()
        cl = QVBoxLayout(container)
        cl.setContentsMargins(8, 8, 8, 8)
        cl.addWidget(v_split)
        return container

    # -- project list / selection ----------------------------------------
    def refresh_project_list(self) -> None:
        """Rebuild the selector from disk, preserving the current selection."""
        current_path = self.state.current_path
        refs = discover_projects(self._projects_dir)

        self.selector.blockSignals(True)
        self.selector.clear()
        self.selector.addItem(_NO_SELECTION, userData=None)
        for ref in refs:
            self.selector.addItem(ref.name, userData=str(ref.path))
        if current_path is not None:
            idx = self.selector.findData(str(current_path))
            if idx >= 0:
                self.selector.setCurrentIndex(idx)
        self.selector.blockSignals(False)

        self.updates_pane.set_projects(refs)
        if self._material_window is not None:
            self._material_window.refresh_projects()

    def _on_selector_changed(self, _index: int) -> None:
        path = self.selector.currentData()
        if path is None:
            self.state.clear()
        else:
            self.state.open_project(path)
        self._rewatch_current_file()

    def _on_project_changed(self, loaded) -> None:
        name = loaded.project.project.name if loaded else "PE Suite"
        self.setWindowTitle(f"PE Suite — {name}" if loaded else "PE Suite")

    def _on_load_failed(self, path, message: str) -> None:
        self.statusBar().showMessage(f"Failed to load {Path(path).name}: {message}", 8000)

    # -- file watching ----------------------------------------------------
    def _setup_watcher(self) -> None:
        self._watcher = QFileSystemWatcher(self)
        if self._projects_dir.is_dir():
            self._watcher.addPath(str(self._projects_dir))
        self._watcher.directoryChanged.connect(self._on_dir_changed)
        self._watcher.fileChanged.connect(self._on_file_changed)

        # Debounce: atomic saves fire several rapid events; coalesce into one reload.
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(180)
        self._reload_timer.timeout.connect(self._do_reload)

    def _rewatch_current_file(self) -> None:
        watched = set(self._watcher.files())
        if watched:
            self._watcher.removePaths(list(watched))
        p = self.state.current_path
        if p is not None and Path(p).exists():
            self._watcher.addPath(str(p))

    def _on_dir_changed(self, _path: str) -> None:
        # Projects added/removed: rebuild the list. Re-arm current file in case an
        # atomic save replaced it. Then reload the current project (debounced).
        self.refresh_project_list()
        self._rewatch_current_file()
        self._reload_timer.start()

    def _on_file_changed(self, _path: str) -> None:
        self._reload_timer.start()

    def _do_reload(self) -> None:
        self.state.reload()
        self._rewatch_current_file()  # atomic save may have dropped the watch

    # -- actions ----------------------------------------------------------
    def open_material_tracking(self) -> None:
        if self._material_window is None:
            self._material_window = MaterialTrackingWindow(
                self._projects_dir, self._fetch, parent=self)
        self._material_window.show()
        self._material_window.raise_()
        self._material_window.activateWindow()

    def _on_launch_editor(self) -> None:
        if self.state.current_path is None:
            self.statusBar().showMessage("Select a project first.", 4000)
            return
        self._editor.launch(self.state.current_path)

    def closeEvent(self, event) -> None:
        self._editor.shutdown()
        self._fetch.shutdown()
        super().closeEvent(event)
