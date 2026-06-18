"""Phase 3 verification: prove the Gantt paints, and capture a visual preview.

Renders the full window (and the Gantt alone) to PNGs using the offscreen platform —
no display needed — so the painting code is actually exercised and the result can be
eyeballed. Also asserts the chart built rows + a date range and produced non-blank pixels.

    .venv/Scripts/python.exe scripts/verify_gantt.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pesuite import config  # noqa: E402
from pesuite.app.main_window import MainWindow  # noqa: E402
from pesuite.app.state import AppState  # noqa: E402
from pesuite.app.theme import apply_theme  # noqa: E402

OUT = ROOT / "scripts" / "_preview"
OUT.mkdir(exist_ok=True)
checks: list[tuple[str, bool]] = []


def check(label: str, ok: bool) -> None:
    checks.append((label, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


def non_background_ratio(img: QImage) -> float:
    """Fraction of pixels that aren't the window background — a crude 'did it draw' test."""
    bg = QColor("#f3f4f7").rgb()
    w, h = img.width(), img.height()
    if w == 0 or h == 0:
        return 0.0
    step = max(1, min(w, h) // 200)
    total = drawn = 0
    for y in range(0, h, step):
        for x in range(0, w, step):
            total += 1
            if (img.pixel(x, y) & 0x00FFFFFF) != (bg & 0x00FFFFFF):
                drawn += 1
    return drawn / total if total else 0.0


def main() -> int:
    app = QApplication([])
    apply_theme(app)
    win = MainWindow(AppState(), projects_dir=config.projects_dir())
    win.resize(1440, 900)
    win.show()

    # Select the richer demo (multi-location, parents, dependencies).
    target = next(i for i in range(win.selector.count())
                  if "npde" in str(win.selector.itemData(i) or "").lower())
    win.selector.setCurrentIndex(target)
    app.processEvents()

    chart = win.gantt_pane._chart
    check("chart built rows", len(chart._rows) > 0)
    check("chart computed a date range", chart._start is not None and chart._num_days > 0)
    check("chart found dependency edges", len(chart._edges) > 0)
    check("chart reports data", chart.has_data())

    full = win.grab()
    full.save(str(OUT / "full_window.png"))
    gantt = win.gantt_pane.grab()
    gantt.save(str(OUT / "gantt_pane.png"))
    prio = win.priorities_pane.grab()
    prio.save(str(OUT / "priorities_pane.png"))

    ratio = non_background_ratio(gantt.toImage())
    check(f"gantt pane painted real content (non-bg ratio {ratio:.2f})", ratio > 0.15)
    check("preview PNGs written", (OUT / "full_window.png").exists())

    print()
    failed = [l for l, ok in checks if not ok]
    if failed:
        print(f"RESULT: {len(failed)} check(s) failed.")
        return 1
    print(f"RESULT: all {len(checks)} checks passed.  Previews in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
