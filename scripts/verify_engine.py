"""Phase 1 verification: prove the engine read layer end-to-end.

Loads each demo project through `pesuite.core`, computes the schedule + critical path,
and renders the derived Tasks and Priorities views — the exact data the UI panes will
consume. Run from the repo root:

    .venv/Scripts/python.exe scripts/verify_engine.py

Exits non-zero if any project fails to load or derive, so it doubles as a smoke test.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Make `pesuite` importable when run from the repo root without installation.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Quiet the engine's INFO logging so the report is readable.
logging.disable(logging.INFO)

from pesuite.core import discover_projects, load_project, priorities, task_rows  # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "pmsuite" / "examples"

INDENT = "    "
BADGE = {
    "complete": "[done]",
    "overdue": "[OVERDUE]",
    "in_progress": "[active]",
    "due_soon": "[soon]",
    "upcoming": "[upcoming]",
    "unscheduled": "[unscheduled]",
}


def fmt_date(d) -> str:
    return d.isoformat() if d else "--"


def report(path: Path) -> None:
    loaded = load_project(path)
    p = loaded.project

    print(f"\n{'=' * 78}")
    print(f"PROJECT  {p.project.name}  ({p.project.id})")
    print(f"file     {path.name}")
    print(f"today    {loaded.today}   project end {fmt_date(loaded.project_end)}")
    print(f"tasks    {len(p.tasks)}   critical {len(loaded.critical.critical_task_ids)}")
    print("=" * 78)

    print("\nTASKS")
    for row in task_rows(loaded):
        pad = INDENT * row.depth
        star = " *" if row.is_critical else ""
        dates = f"{fmt_date(row.start)} -> {fmt_date(row.finish)}"
        name = ("> " + row.name) if row.is_parent else row.name
        print(f"  {pad}{name}{star}")
        print(f"  {pad}{INDENT}{BADGE[row.status.value]:<12} {dates}  @{row.location or '--'}")

    print("\nPRIORITIES  (critical-path long pole, actionable, incomplete)")
    items = priorities(loaded)
    if not items:
        print("  (none — no incomplete critical tasks)")
    for it in items:
        extra = ""
        if it.days_overdue:
            extra = f"  {it.days_overdue}d overdue"
        elif it.days_until_start:
            extra = f"  starts in {it.days_until_start}d"
        print(f"  {it.rank}. {it.name}  {BADGE[it.status.value]}"
              f"  ({fmt_date(it.start)} -> {fmt_date(it.finish)}){extra}")


def main() -> int:
    print("Discoverable projects in pmsuite/examples:")
    for ref in discover_projects(EXAMPLES):
        print(f"  - {ref.name}  ({ref.id})  [{ref.path.name}]")

    failures = 0
    for json_path in sorted(EXAMPLES.glob("*.json")):
        try:
            report(json_path)
        except Exception as exc:  # noqa: BLE001 — surface any failure as a test failure
            failures += 1
            print(f"\n!! FAILED on {json_path.name}: {type(exc).__name__}: {exc}")

    print(f"\n{'=' * 78}")
    if failures:
        print(f"RESULT: {failures} project(s) failed.")
        return 1
    print("RESULT: all projects loaded and derived successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
