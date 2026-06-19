"""Phases 6 & 7 verification: the Updates pane and the Material pane/window.

Proves the Updates pane renders fetched records (populated via a throwaway in-test source
written straight to the store — the app ships no fabricated sources), that the Material
pane shows one project box per project and launching opens a per-project window, and that
a refresh round-trips through the client's out-of-process runner.

    .venv/Scripts/python.exe scripts/verify_ui_fetch.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pesuite import config  # noqa: E402
from pesuite.core import discover_projects  # noqa: E402
from pesuite.fetch_client import FetchClient  # noqa: E402
from pesuite.app.material_window import MaterialTrackingWindow  # noqa: E402
from pesuite.panes.material_pane import MaterialPane  # noqa: E402
from pesuite.panes.updates_pane import UpdatesPane  # noqa: E402
from fetch_service.models import Record  # noqa: E402
from fetch_service.store import Store  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(label: str, ok: bool) -> None:
    checks.append((label, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


def seed_store(store: Store) -> None:
    """Write a couple of records directly into an already-open store."""
    store.ensure_source("test_src", "Test Source", "updates")
    store.upsert_records("test_src", [
        Record(source_id="test_src", group="updates", kind="announcement",
               key="x", title="Test update", body="hello",
               project_id="DEMO-NPDE", timestamp=datetime.now(timezone.utc)),
    ])
    store.ensure_source("test_mat", "Test Material", "material")
    store.upsert_records("test_mat", [
        Record(source_id="test_mat", group="material", kind="po", key="PO-9",
               title="Test part", project_id="DEMO-NPDE",
               data={"status": "Ordered", "qty": 5, "eta": "2026-07-01",
                     "supplier": "Test", "po": "PO-9"}),
    ])


def main() -> int:
    app = QApplication([])
    # Construct the client FIRST (its self-heal prune runs here), THEN seed test data
    # straight into its store so the seeded rows survive for the rest of the run.
    fetch = FetchClient()
    seed_store(fetch._store)
    refs = discover_projects(config.projects_dir())

    # Updates pane renders cards + source filter.
    updates = UpdatesPane(fetch)
    updates.set_projects(refs)
    updates._reload()
    check("Updates pane rendered update cards", updates._list.count() > 0)
    check("Updates source filter populated", updates._source_filter.count() >= 2)

    # Material pane is a PROJECT PICKER (boxes), not a data table.
    mat = MaterialPane()
    mat.set_projects(refs)
    boxes = mat._grid.count()
    check("Material pane shows a box per project", boxes >= len(refs))

    opened = {}
    mat.openRequested.connect(lambda pid, name: opened.update(id=pid, name=name))
    # click the first project box (grid item 0 is the hint label)
    first_box = None
    for i in range(mat._grid.count()):
        w = mat._grid.itemAt(i).widget()
        if w is not None and hasattr(w, "ref"):
            first_box = w
            break
    first_box.click()
    app.processEvents()
    check("clicking a box requests opening that project", opened.get("id") == first_box.ref.id)

    # The per-project window opens and renders the seeded material row.
    win = MaterialTrackingWindow("DEMO-NPDE", "NPDE", fetch)
    app.processEvents()
    check("Material window table rendered rows", win._table.rowCount() > 0)

    # Round-trip: a real refresh through the client's subprocess runner.
    got = {"group": None, "ok": None}
    loop = QEventLoop()

    def on_ref(group, ok):
        got["group"], got["ok"] = group, ok
        loop.quit()

    fetch.refreshed.connect(on_ref)
    fetch.refresh_group("material", project_id="DEMO-NPDE", force=True)
    to = QTimer(); to.setSingleShot(True); to.timeout.connect(loop.quit); to.start(45000)
    loop.exec()
    check("client refresh round-tripped via runner", got["group"] == "material" and got["ok"])

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
