"""Phases 6 & 7 verification: the Updates pane and Material window render fetched data,
and a refresh round-trips through the client's out-of-process runner.

Populates the store, builds the panes headlessly, asserts they render records, then
fires a real refresh through FetchClient and waits for the `refreshed` signal.

    .venv/Scripts/python.exe scripts/verify_ui_fetch.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pesuite import config  # noqa: E402
from pesuite.core import discover_projects  # noqa: E402
from pesuite.fetch_client import FetchClient  # noqa: E402
from pesuite.panes.material_pane import MaterialPane  # noqa: E402
from pesuite.panes.updates_pane import UpdatesPane  # noqa: E402
from fetch_service.service import refresh_group  # noqa: E402
from fetch_service.source import SourceRegistry  # noqa: E402
from fetch_service.sources import register_all  # noqa: E402
from fetch_service.store import Store  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(label: str, ok: bool) -> None:
    checks.append((label, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


def main() -> int:
    # Populate the real (hidden) store directly so reads have data.
    store = Store(config.fetch_store_path())
    registry = register_all(SourceRegistry())
    refresh_group(store, registry, "updates", force=True)
    refresh_group(store, registry, "material", force=True)
    store.close()

    app = QApplication([])
    fetch = FetchClient()
    refs = discover_projects(config.projects_dir())

    # Updates pane renders cards + source filter.
    updates = UpdatesPane(fetch)
    updates.set_projects(refs)
    updates._reload()
    check("Updates pane rendered update cards", updates._list.count() > 0)
    check("Updates source filter populated", updates._source_filter.count() >= 2)

    # Filter by project narrows the feed.
    idx = updates._project_filter.findData("DEMO-NPDE")
    updates._project_filter.setCurrentIndex(idx)
    app.processEvents()
    check("Updates filter by project works", updates._list.count() > 0)

    # Material pane renders the table for a project.
    mat = MaterialPane(fetch)
    mat.set_projects(refs)
    midx = mat._selector.findData("DEMO-NPDE")
    mat._selector.setCurrentIndex(midx if midx >= 0 else 0)
    app.processEvents()
    check("Material table rendered rows", mat._table.rowCount() > 0)

    # Round-trip: real refresh through the client's subprocess runner.
    got = {"group": None, "ok": None}
    loop = QEventLoop()

    def on_ref(group, ok):
        got["group"], got["ok"] = group, ok
        loop.quit()

    fetch.refreshed.connect(on_ref)
    fetch.refresh_group("updates", force=True)
    to = QTimer(); to.setSingleShot(True); to.timeout.connect(loop.quit); to.start(45000)
    loop.exec()

    check("client refresh round-tripped via runner", got["group"] == "updates" and got["ok"])

    fetch.shutdown()
    print()
    failed = [l for l, ok in checks if not ok]
    if failed:
        print(f"RESULT: {len(failed)} check(s) failed.")
        return 1
    print(f"RESULT: all {len(checks)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
