"""Application UI state: the single source of truth for the selected project.

`AppState` is the hub the global selector writes to and every derived pane listens
to. It holds one `LoadedProject` snapshot at a time and re-emits it on change/reload.
Panes never load projects themselves — they react to `projectChanged`.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from pesuite.core import LoadedProject, load_project


class AppState(QObject):
    """Holds the globally-selected project and notifies panes of changes."""

    # Emits the new LoadedProject, or None when the selection is cleared.
    projectChanged = Signal(object)
    # Emitted when a load fails (path, error message) so the UI can surface it.
    loadFailed = Signal(object, str)

    def __init__(self) -> None:
        super().__init__()
        self._current: LoadedProject | None = None
        self._current_path: Path | None = None

    @property
    def current(self) -> LoadedProject | None:
        return self._current

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    def open_project(self, path: str | Path) -> None:
        """Load `path` and broadcast it. On failure, keep prior state and signal."""
        path = Path(path)
        try:
            loaded = load_project(path)
        except Exception as exc:  # noqa: BLE001 — surface, don't crash the UI
            self.loadFailed.emit(path, f"{type(exc).__name__}: {exc}")
            return
        self._current = loaded
        self._current_path = path
        self.projectChanged.emit(loaded)

    def reload(self) -> None:
        """Re-read the current project from disk (used by file-watch auto-reload)."""
        if self._current_path is not None:
            self.open_project(self._current_path)

    def clear(self) -> None:
        """Clear the selection (panes show their empty state)."""
        self._current = None
        self._current_path = None
        self.projectChanged.emit(None)
