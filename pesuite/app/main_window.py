"""The PE Suite main window: top bar, pane grid, global selector, file-watch.

Layout:

    +-------------------------------------------------------------+
    |  PE Suite        Project [ ... v]                           |  top bar
    +----------------------------+--------------------------------+
    |                            |  Priorities                    |
    |  Gantt Chart               +--------------------------------+
    |                            |  Material Tracking             |
    +-------------+--------------+--------------------------------+
    |  Tasks      |  Updates                                      |
    +-------------+-----------------------------------------------+

The global selector lives in the TOP BAR (app-level), not in any pane, and drives
Gantt + Tasks + Priorities through AppState. Updates and Material Tracking keep their
own independent filters/selectors. Every pane can be maximized to fill the window via
its header button. A QFileSystemWatcher auto-reloads on edits to projects/.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from pesuite import config
from pesuite.app.editor_launcher import StreamlitEditor
from pesuite.app.material_window import MaterialTrackingWindow
from pesuite.app.state import AppState
from pesuite.core import discover_projects
from pesuite.fetch_client import FetchClient
from pesuite.panes import (
    GanttPane,
    MaterialPane,
    PrioritiesPane,
    TasksPane,
    UpdatesPane,
)

_NO_SELECTION = "— Select project —"


class _MaximizedWindow(QMainWindow):
    """Hosts a single pane shown maximized; calls back on close to restore it."""

    def __init__(self, on_close) -> None:
        super().__init__()
        self._on_close = on_close

    def closeEvent(self, event) -> None:
        self._on_close()
        event.ignore()  # the pane must be reparented back, not destroyed


class MainWindow(QMainWindow):
    def __init__(self, state: AppState | None = None, projects_dir: Path | None = None) -> None:
        super().__init__()
        self.state = state or AppState()
        self._projects_dir = Path(projects_dir or config.projects_dir())

        # Maximize state: (pane, splitter, index) while a pane is popped out.
        self._maximized: tuple | None = None
        self._max_window: _MaximizedWindow | None = None
        # Open Material Tracking windows, keyed by project id.
        self._material_windows: dict[str, MaterialTrackingWindow] = {}

        # Services the panes depend on must exist before the panes are built.
        self._fetch = FetchClient(parent=self)
        self._editor = StreamlitEditor(config.streamlit_script(), parent=self)
        self._editor.statusChanged.connect(lambda m: self.statusBar().showMessage(m, 6000))
        self._editor.failed.connect(lambda m: self.statusBar().showMessage(m, 8000))

        self.setWindowTitle("PE Suite")
        self.resize(1480, 940)

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
        bar.setFixedHeight(54)
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(18, 0, 18, 0)
        hl.setSpacing(10)

        title = QLabel("PE Suite")
        title.setObjectName("appTitle")
        hl.addWidget(title)
        hl.addSpacing(26)

        lbl = QLabel("Project")
        lbl.setObjectName("topBarLabel")
        hl.addWidget(lbl)

        self.selector = QComboBox()
        self.selector.setMinimumWidth(340)
        self.selector.currentIndexChanged.connect(self._on_selector_changed)
        hl.addWidget(self.selector)

        hl.addStretch(1)
        return bar

    # -- panes ------------------------------------------------------------
    def _build_panes(self) -> QWidget:
        self.gantt_pane = GanttPane(self.state)
        self.priorities_pane = PrioritiesPane(self.state)
        self.material_pane = MaterialPane()
        self.tasks_pane = TasksPane(self.state)
        self.updates_pane = UpdatesPane(self._fetch)

        self.gantt_pane.launchEditorRequested.connect(self._on_launch_editor)
        self.material_pane.openRequested.connect(self._open_material_window)

        # Right column: Priorities (top) over Material Tracking (bottom).
        self.right_split = QSplitter(Qt.Vertical)
        self.right_split.addWidget(self.priorities_pane)
        self.right_split.addWidget(self.material_pane)
        self.right_split.setSizes([460, 320])

        # Top row: Gantt (left) beside the right column.
        self.top_split = QSplitter(Qt.Horizontal)
        self.top_split.addWidget(self.gantt_pane)
        self.top_split.addWidget(self.right_split)
        self.top_split.setSizes([980, 480])

        # Bottom row: Tasks beside Updates.
        self.bottom_split = QSplitter(Qt.Horizontal)
        self.bottom_split.addWidget(self.tasks_pane)
        self.bottom_split.addWidget(self.updates_pane)
        self.bottom_split.setSizes([720, 720])

        self.main_split = QSplitter(Qt.Vertical)
        self.main_split.addWidget(self.top_split)
        self.main_split.addWidget(self.bottom_split)
        self.main_split.setSizes([600, 320])

        # Wire every pane's maximize button.
        for pane in (self.gantt_pane, self.priorities_pane, self.material_pane,
                     self.tasks_pane, self.updates_pane):
            pane.maximizeRequested.connect(lambda p=pane: self._toggle_maximize(p))

        container = QWidget()
        cl = QVBoxLayout(container)
        cl.setContentsMargins(10, 10, 10, 10)
        cl.addWidget(self.main_split)
        return container

    # -- maximize / restore ----------------------------------------------
    def _toggle_maximize(self, pane) -> None:
        if self._maximized is not None and self._maximized[0] is pane:
            self._restore_pane()
            return
        if self._maximized is not None:
            self._restore_pane()

        splitter = pane.parentWidget()
        # parentWidget() of a splitter child is the QSplitter itself.
        index = splitter.indexOf(pane) if isinstance(splitter, QSplitter) else -1
        if index < 0:
            return
        self._maximized = (pane, splitter, index)

        self._max_window = _MaximizedWindow(self._restore_pane)
        self._max_window.setWindowTitle(f"PE Suite — {pane.title}")
        self._max_window.setCentralWidget(pane)  # reparents the pane
        pane.set_maximized(True)
        self._max_window.resize(self.size())
        self._max_window.showMaximized()

    def _restore_pane(self) -> None:
        if self._maximized is None:
            return
        pane, splitter, index = self._maximized
        splitter.insertWidget(index, pane)  # reparents back into the grid
        pane.set_maximized(False)
        self._maximized = None
        if self._max_window is not None:
            win, self._max_window = self._max_window, None
            win.deleteLater()

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
        self.material_pane.set_projects(refs)

    def _on_selector_changed(self, _index: int) -> None:
        path = self.selector.currentData()
        if path is None:
            self.state.clear()
        else:
            self.state.open_project(path)
        self._rewatch_current_file()

    def _on_project_changed(self, loaded) -> None:
        name = loaded.project.project.name if loaded else None
        self.setWindowTitle(f"PE Suite — {name}" if name else "PE Suite")

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
        self.refresh_project_list()
        self._rewatch_current_file()
        self._reload_timer.start()

    def _on_file_changed(self, _path: str) -> None:
        self._reload_timer.start()

    def _do_reload(self) -> None:
        self.state.reload()
        self._rewatch_current_file()  # atomic save may have dropped the watch

    # -- actions ----------------------------------------------------------
    def _open_material_window(self, project_id: str, project_name: str) -> None:
        """Open (or focus) the Material Tracking window for one project."""
        win = self._material_windows.get(project_id)
        if win is None:
            win = MaterialTrackingWindow(project_id, project_name, self._fetch, parent=self)
            win.closed.connect(self._material_windows.pop)
            win.setAttribute(Qt.WA_DeleteOnClose)
            self._material_windows[project_id] = win
        win.show()
        win.raise_()
        win.activateWindow()

    def _on_launch_editor(self) -> None:
        if self.state.current_path is None:
            self.statusBar().showMessage("Select a project first.", 4000)
            return
        self._editor.launch(self.state.current_path)

    def closeEvent(self, event) -> None:
        if self._maximized is not None:
            self._restore_pane()
        for win in list(self._material_windows.values()):
            win.close()
        self._editor.shutdown()
        self._fetch.shutdown()
        super().closeEvent(event)
