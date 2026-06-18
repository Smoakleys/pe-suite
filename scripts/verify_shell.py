"""Phase 2 verification: build the shell headlessly and prove the wiring works.

Runs Qt with the 'offscreen' platform (no display needed), constructs the main window
pointed at projects/, and asserts:
  - the global selector lists the discovered projects
  - selecting a project populates Gantt + Tasks + Priorities (global selector wiring)
  - clearing the selection returns panes to their empty state
  - reload() re-derives from disk (the path file-watch triggers)
  - the Material Tracking window opens as a separate window

    .venv/Scripts/python.exe scripts/verify_shell.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from pesuite import config  # noqa: E402
from pesuite.app.main_window import MainWindow  # noqa: E402
from pesuite.app.state import AppState  # noqa: E402

PROJECTS = config.projects_dir()

checks: list[tuple[str, bool]] = []


def check(label: str, ok: bool) -> None:
    checks.append((label, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


def main() -> int:
    app = QApplication([])
    state = AppState()
    win = MainWindow(state, projects_dir=PROJECTS)

    # Selector lists the two demo projects (+ the placeholder row).
    n_items = win.selector.count()
    check(f"selector lists projects (got {n_items} incl. placeholder)", n_items >= 3)

    # Select the NPDE project by matching its file path.
    target = None
    for i in range(win.selector.count()):
        data = win.selector.itemData(i)
        if data and "npde" in str(data).lower():
            target = i
            break
    check("found NPDE project in selector", target is not None)
    win.selector.setCurrentIndex(target)
    app.processEvents()

    loaded = state.current
    check("global selection loaded a project", loaded is not None)
    check("Tasks pane populated", win.tasks_pane._tree.topLevelItemCount() > 0)
    check("Priorities pane populated", win.priorities_pane._list.count() > 0)
    check("Gantt pane left placeholder (content shown)",
          win.gantt_pane._stack.currentIndex() == 1)
    check("Updates filter knows the projects",
          win.updates_pane._project_filter.count() >= 3)

    # Clear -> panes return to empty state.
    win.selector.setCurrentIndex(0)
    app.processEvents()
    check("clearing selection empties Tasks", win.tasks_pane._tree.topLevelItemCount() == 0)
    check("clearing selection empties Priorities", win.priorities_pane._list.count() == 0)

    # Reload path (what the file-watch auto-reload calls).
    win.selector.setCurrentIndex(target)
    app.processEvents()
    before = state.current
    state.reload()
    app.processEvents()
    check("reload() re-derived the project", state.current is not None and state.current is not before)

    # Material Tracking opens as its own window.
    win.open_material_tracking()
    app.processEvents()
    mw = win._material_window
    check("Material Tracking window created", mw is not None)
    check("Material window has its own selector", mw is not None and mw._selector.count() >= 2)

    print()
    failed = [label for label, ok in checks if not ok]
    if failed:
        print(f"RESULT: {len(failed)} check(s) failed.")
        return 1
    print(f"RESULT: all {len(checks)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
