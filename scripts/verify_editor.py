"""Phase 4 verification: prove Launch Editor really starts Streamlit and targets the
selected project — without opening a browser.

Starts the editor via StreamlitEditor with an injected URL opener (so nothing pops up),
waits for the managed server to become ready, asserts the per-project URL is correct,
then shuts the server down and confirms it stopped.

    .venv/Scripts/python.exe scripts/verify_editor.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import unquote

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pesuite import config  # noqa: E402
from pesuite.app.editor_launcher import StreamlitEditor, _free_port, _project_query_value  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(label: str, ok: bool) -> None:
    checks.append((label, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


def main() -> int:
    app = QApplication([])

    # Pure-unit checks first (no server needed).
    proj = config.projects_dir() / "small_demo.json"
    check("test project exists", proj.exists())
    qv = _project_query_value(proj)
    check("query value maps to projects/<file>", unquote(qv) == "projects/small_demo.json")
    check("free-port finder returns a port", isinstance(_free_port(), int))
    check("editor script resolves", config.streamlit_script().exists())

    # End-to-end: start the real server, capture the URL, no browser.
    opened: list[str] = []
    editor = StreamlitEditor(config.streamlit_script(), open_url=opened.append)
    editor.statusChanged.connect(lambda m: print(f"    · {m}"))
    editor.failed.connect(lambda m: print(f"    ! {m}"))

    editor.launch(proj)

    loop = QEventLoop()
    state = {"done": False}

    def poll() -> None:
        if editor._ready or opened:
            state["done"] = True
            loop.quit()

    pt = QTimer(); pt.timeout.connect(poll); pt.start(200)
    to = QTimer(); to.setSingleShot(True); to.timeout.connect(loop.quit); to.start(60000)
    loop.exec()
    pt.stop()

    check("server became ready", editor._ready)
    check("a URL was opened for the project", len(opened) >= 1)
    if opened:
        url = opened[0]
        check("URL points at the running server", f":{editor._port}/" in url)
        check("URL carries the project query", "small_demo.json" in unquote(url))
        print(f"    opened: {unquote(opened[0])}")

    editor.shutdown()
    app.processEvents()
    check("server shut down", not editor.is_running())

    print()
    failed = [l for l, ok in checks if not ok]
    if failed:
        print(f"RESULT: {len(failed)} check(s) failed.")
        return 1
    print(f"RESULT: all {len(checks)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
