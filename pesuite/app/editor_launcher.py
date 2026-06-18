"""Launch the Streamlit editor for the selected project.

The editor is a separate app (PMSuite's Streamlit UI). PE Suite starts it once as a
managed child process and opens the system browser at a per-project URL. The Streamlit
app auto-loads the project from a `?project=projects/<file>` query param, and because
each browser tab is its own Streamlit session, opening a new tab always loads the
requested project — even if another tab has a different one open.

Design notes:
- QProcess (not subprocess) so the server integrates with the Qt event loop and is
  cleaned up with the app.
- Readiness is polled with a QTimer (non-blocking) — the UI never freezes while the
  server boots.
- `open_url` is injectable so tests can launch the real server without a browser popup.
"""

from __future__ import annotations

import socket
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QObject, QProcess, QTimer, Signal


def _free_port(preferred: int = 8501, span: int = 25) -> int:
    """First bindable port at/after `preferred`; falls back to `preferred`."""
    for port in range(preferred, preferred + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return preferred


def _port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _project_query_value(project_path: Path) -> str:
    """Map a project file to the editor's expected ref ('projects/<file>' or
    'examples/<file>'), URL-encoded for the query string."""
    parent = project_path.parent.name
    prefix = parent if parent in ("projects", "examples") else "projects"
    return quote(f"{prefix}/{project_path.name}", safe="")


class StreamlitEditor(QObject):
    """Manages one Streamlit server process and opens per-project browser tabs."""

    statusChanged = Signal(str)
    failed = Signal(str)

    MAX_POLLS = 75  # ~30s at 400ms

    def __init__(self, script: Path, parent: QObject | None = None,
                 open_url=webbrowser.open) -> None:
        super().__init__(parent)
        self._script = Path(script)
        self._open_url = open_url
        self._proc: QProcess | None = None
        self._port: int | None = None
        self._ready = False
        self._shutting_down = False
        self._pending: list[str] = []
        self._polls = 0

        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._poll_ready)

    # -- public ----------------------------------------------------------
    def launch(self, project_path: Path) -> None:
        """Open the editor for `project_path`, starting the server if needed."""
        if not self._script.exists():
            self.failed.emit(f"Editor script not found: {self._script}")
            return
        url = self._url_for(project_path)
        if self._ready and self._proc and self._proc.state() != QProcess.NotRunning:
            self._open(url)
            return
        self._pending.append(url)
        self._ensure_started()

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.state() != QProcess.NotRunning

    def shutdown(self) -> None:
        self._shutting_down = True
        self._timer.stop()
        if self._proc and self._proc.state() != QProcess.NotRunning:
            self._proc.terminate()
            if not self._proc.waitForFinished(2500):
                self._proc.kill()
                self._proc.waitForFinished(1500)
        self._proc = None
        self._ready = False

    # -- internals -------------------------------------------------------
    def _url_for(self, project_path: Path) -> str:
        return (f"http://127.0.0.1:{self._port}/"
                f"?project={_project_query_value(Path(project_path))}")

    def _ensure_started(self) -> None:
        if self.is_running():
            self.statusChanged.emit("Editor starting…")
            return
        self._port = _free_port()
        # Rebuild any pending URLs now that we know the port.
        self._pending = [u.replace("http://127.0.0.1:None/", f"http://127.0.0.1:{self._port}/")
                         for u in self._pending]

        self._proc = QProcess(self)
        self._proc.setProgram(sys.executable)
        self._proc.setArguments([
            "-m", "streamlit", "run", str(self._script),
            "--server.headless=true",
            f"--server.port={self._port}",
            "--server.address=127.0.0.1",
            "--browser.gatherUsageStats=false",
        ])
        self._proc.setWorkingDirectory(str(self._script.parent.parent))
        self._proc.finished.connect(self._on_proc_finished)
        self._proc.errorOccurred.connect(self._on_proc_error)

        self._ready = False
        self._polls = 0
        self.statusChanged.emit("Starting editor…")
        self._proc.start()
        self._timer.start()

    def _poll_ready(self) -> None:
        self._polls += 1
        if self._port is not None and _port_listening(self._port):
            self._ready = True
            self._timer.stop()
            self.statusChanged.emit("Editor ready — opening in your browser…")
            self._flush_pending()
            return
        if self._polls >= self.MAX_POLLS:
            self._timer.stop()
            self.failed.emit("Editor did not start in time.")

    def _flush_pending(self) -> None:
        # Open the most recent request (and any others queued during boot).
        for url in self._pending:
            self._open(url)
        self._pending.clear()

    def _open(self, url: str) -> None:
        # Make sure a stale "None" port never leaks into a URL.
        if self._port is not None:
            url = url.replace(":None/", f":{self._port}/")
        self._open_url(url)

    def _on_proc_finished(self, _code: int, _status) -> None:
        if self._shutting_down:
            return
        if not self._ready:
            self.failed.emit("Editor process exited before it was ready.")
        self._ready = False

    def _on_proc_error(self, _error) -> None:
        if self._shutting_down:
            return
        self._timer.stop()
        self.failed.emit("Failed to start the editor process.")
