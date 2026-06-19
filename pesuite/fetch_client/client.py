"""FetchClient: read the store, trigger out-of-process refreshes.

Reads are synchronous and instant (cache-first). Refreshes spawn `fetch_service.runner`
as a managed QProcess and emit `refreshed(group)` when it finishes, so panes can reload.
Several refreshes can be in flight; each is tracked and cleaned up on completion.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QProcess, Signal

from pesuite import config
from fetch_service.models import SourceInfo, UpdateRow
from fetch_service.store import Store


class FetchClient(QObject):
    # Emitted (group) when a refresh process finishes; ok=False if it failed to run.
    refreshed = Signal(str, bool)
    refreshStarted = Signal(str)

    def __init__(self, parent: QObject | None = None, store_path=None) -> None:
        super().__init__(parent)
        self._store = Store(store_path or config.fetch_store_path())
        self._procs: dict[QProcess, str] = {}
        self._shutting_down = False

    # -- reads -----------------------------------------------------------
    def sources(self) -> list[SourceInfo]:
        return self._store.list_sources()

    def source_names(self) -> dict[str, str]:
        return {s.id: s.name for s in self._store.list_sources()}

    def updates(self, project_id: str | None = None,
                source_id: str | None = None) -> list[UpdateRow]:
        return self._store.get_updates(project_id=project_id, source_id=source_id)

    def materials(self, project_id: str | None = None) -> list[dict]:
        return self._store.get_records("material", project_id=project_id)

    # -- refresh (out-of-process) ---------------------------------------
    def refresh_group(self, group: str, project_id: str | None = None,
                      force: bool = True, network: bool = False) -> None:
        proc = QProcess(self)
        proc.setProgram(sys.executable)
        args = ["-m", "fetch_service.runner", "--group", group]
        if project_id:
            args += ["--project", project_id]
        if force:
            args.append("--force")
        if network:
            args.append("--network")
        proc.setArguments(args)
        proc.setWorkingDirectory(str(config.REPO_ROOT))
        proc.finished.connect(lambda code, _st, p=proc: self._on_finished(p, code))
        proc.errorOccurred.connect(lambda _e, p=proc: self._on_error(p))
        self._procs[proc] = group
        self.refreshStarted.emit(group)
        proc.start()

    def _on_finished(self, proc: QProcess, code: int) -> None:
        if self._shutting_down:
            return
        group = self._procs.pop(proc, "")
        if group:
            self.refreshed.emit(group, code == 0)

    def _on_error(self, proc: QProcess) -> None:
        # Killing a process during shutdown fires errorOccurred; ignore it then.
        if self._shutting_down:
            return
        group = self._procs.pop(proc, "")
        if group:
            self.refreshed.emit(group, False)

    def shutdown(self) -> None:
        self._shutting_down = True
        for proc in list(self._procs):
            if proc.state() != QProcess.NotRunning:
                proc.kill()
                proc.waitForFinished(1500)
        self._procs.clear()
        self._store.close()
