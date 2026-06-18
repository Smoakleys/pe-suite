"""Build a large, detailed, long-horizon demo project via the real engine.

Produces pmsuite/projects/asic_program.json with the EXACT structure of the existing
demo files (it is created and saved through gantt_builder's own API, so the schema,
IDs, baselines, and holiday seeding are all engine-authored — not hand-typed).

The program is an ~18-month automotive/space-grade ASIC New Product Development &
Engineering (NPDE) effort spanning all eight locations, with phase-summary parents, all
four dependency types (FS/SS/FF/SF) with lags, a mix of working_days and e_days tasks,
seeded holidays for 2026-2028, and several already-completed early tasks (one with a
manual delay) so the completion / delay_log fields are exercised too.

    .venv/Scripts/python.exe scripts/build_demo_program.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gantt_builder import api  # noqa: E402
from gantt_builder.locations import DEFAULT_WORK_WEEKS, seed_holidays  # noqa: E402
from gantt_builder.models import (  # noqa: E402
    Dependency,
    HolidayEntry,
    Project,
    ProjectMeta,
    Settings,
    Task,
)

OUT = ROOT / "pmsuite" / "projects" / "asic_program.json"
YEAR_START, YEAR_END = 2026, 2028
TZ = "America/Chicago"
PROGRAM_START = "2026-08-03"  # first Monday in August 2026

# Locations used across the program (all eight in the enum).
LOCATIONS = ["DAL", "FR-BIP", "MLA", "TIEMA", "CLARK", "TIPI", "TAI", "AIZU"]

# Each task: key, name, location, calendar_mode, cycle_time, parent_key, [deps].
# deps are (predecessor_key, type, lag_days). Parents have cycle_time=None.
# Ordered so every parent appears before its children.
PARENTS = [
    ("P0", "Phase 0 — Program Setup"),
    ("P1", "Phase 1 — Design"),
    ("P2", "Phase 2 — Wafer Fabrication"),
    ("P3", "Phase 3 — Assembly & Packaging"),
    ("P4", "Phase 4 — Test & Burn-in"),
    ("P5", "Phase 5 — Qualification"),
    ("P6", "Phase 6 — Documentation"),
    ("P7", "Phase 7 — Customer & Closeout"),
]

# (key, name, location, mode, cycle, parent, deps)
LEAVES = [
    # Phase 0 — Setup (these get marked complete after baselining)
    ("kickoff", "Program kickoff", "DAL", "working_days", 1, "P0", []),
    ("reqs", "Requirements & spec freeze", "DAL", "working_days", 12, "P0",
     [("kickoff", "FS", 0)]),
    ("dplan", "Design plan & DFMEA", "DAL", "working_days", 8, "P0",
     [("reqs", "FS", 0)]),

    # Phase 1 — Design
    ("rtl", "RTL / schematic design", "DAL", "working_days", 25, "P1",
     [("dplan", "FS", 0)]),
    ("verif", "Verification & simulation", "DAL", "working_days", 22, "P1",
     [("rtl", "SS", 5)]),                                  # SS with lag
    ("layout", "Mask layout & DRC", "FR-BIP", "working_days", 18, "P1",
     [("rtl", "FS", 0)]),
    ("tapeout", "Tapeout design review (gate)", "DAL", "working_days", 2, "P1",
     [("layout", "FS", 0), ("verif", "FS", 0)]),

    # Phase 2 — Wafer fab (e_days; long lead)
    ("maskset", "Mask set fabrication", "TAI", "e_days", 14, "P2",
     [("tapeout", "FS", 0)]),
    ("lotA", "Wafer fab — Lot A", "TAI", "e_days", 45, "P2",
     [("maskset", "FS", 0)]),
    ("lotB", "Wafer fab — Lot B", "TAI", "e_days", 45, "P2",
     [("lotA", "SS", 10)]),                                # staggered split-lot
    ("lotC", "Wafer fab — Lot C (risk buffer)", "TAI", "e_days", 45, "P2",
     [("lotB", "SS", 10)]),
    ("wsort", "Wafer sort / e-test", "TAI", "working_days", 6, "P2",
     [("lotA", "FS", 0), ("lotB", "FS", 0)]),

    # Phase 3 — Assembly (substrate is a long-lead parallel buy)
    ("substrate", "Substrate procurement (long lead)", "CLARK", "e_days", 60, "P3",
     [("tapeout", "FS", 0)]),
    ("dicing", "Wafer prep & dicing", "MLA", "working_days", 4, "P3",
     [("wsort", "FS", 0)]),
    ("asm1", "Package assembly — Kuala Lumpur", "MLA", "working_days", 9, "P3",
     [("dicing", "FS", 0), ("substrate", "FF", 2)]),       # FF with lag
    ("asm2", "Package assembly — Melaka (2nd source)", "TIEMA", "working_days", 9, "P3",
     [("asm1", "SS", 2)]),

    # Phase 4 — Test & burn-in
    ("progdev", "Final test program development", "TIPI", "working_days", 20, "P4",
     [("tapeout", "FS", 0)]),
    ("burnin", "Burn-in (oven)", "AIZU", "e_days", 7, "P4",
     [("asm1", "FS", 0)]),
    ("prodtest", "Production test", "MLA", "working_days", 10, "P4",
     [("burnin", "FS", 0), ("progdev", "FF", 0)]),
    ("htestrig", "JIT hi-temp test rig build", "TIPI", "working_days", 6, "P4",
     [("prodtest", "SF", 0)]),                             # SF (just-in-time)
    ("charac", "Device characterization", "DAL", "working_days", 12, "P4",
     [("prodtest", "FS", 0)]),

    # Phase 5 — Qualification (e_days, long)
    ("htol", "Reliability qual — HTOL", "DAL", "e_days", 30, "P5",
     [("charac", "FS", 0)]),
    ("tempcyc", "Temp cycle qual", "AIZU", "e_days", 25, "P5",
     [("htol", "SS", 0)]),
    ("esd", "ESD / latch-up qual", "FR-BIP", "working_days", 8, "P5",
     [("charac", "FS", 0)]),
    ("qualrev", "Qualification data review", "DAL", "working_days", 3, "P5",
     [("htol", "FS", 0), ("tempcyc", "FS", 0), ("esd", "FS", 0)]),

    # Phase 6 — Documentation
    ("datasheet", "Datasheet", "DAL", "working_days", 10, "P6",
     [("charac", "FS", 0)]),
    ("qualrpt", "Qualification report", "DAL", "working_days", 5, "P6",
     [("qualrev", "FS", 0)]),
    ("tidrpt", "TID / radiation report", "DAL", "working_days", 2, "P6",
     [("qualrev", "FS", 0)]),
    ("appnotes", "Application notes", "DAL", "working_days", 8, "P6",
     [("datasheet", "FS", 0)]),

    # Phase 7 — Customer & closeout
    ("samples", "Customer sample shipment", "DAL", "working_days", 1, "P7",
     [("datasheet", "FS", 0), ("prodtest", "FS", 0)]),
    ("custeval", "Customer evaluation", "DAL", "e_days", 30, "P7",
     [("samples", "FS", 0)]),
    ("ppap", "PPAP submission", "DAL", "working_days", 5, "P7",
     [("qualrpt", "FS", 0), ("custeval", "FS", 0)]),
    ("release", "Production release gate", "DAL", "working_days", 1, "P7",
     [("ppap", "FS", 0)]),
    ("closeout", "Program closeout review", "DAL", "working_days", 1, "P7",
     [("release", "FS", 0)]),
]


def build() -> Project:
    now = datetime.now(timezone.utc).astimezone()

    holidays = {
        loc: [HolidayEntry.model_validate(h)
              for h in seed_holidays(loc, YEAR_START, YEAR_END)]
        for loc in LOCATIONS
    }
    work_weeks = {loc: DEFAULT_WORK_WEEKS[loc] for loc in LOCATIONS}

    meta = ProjectMeta(
        id="DEMO-ASIC-PROGRAM",
        name="Rad-Hard ASIC Program (Full NPDE)",
        timezone=TZ,
        created_at=now,
        updated_at=now,
    )
    settings = Settings(holidays=holidays, work_weeks=work_weeks)
    project = Project(project=meta, settings=settings, tasks=[])

    # Assign sequential TASK-NNN ids in declaration order (parents first).
    key_to_id: dict[str, str] = {}
    ordered: list[tuple] = [(k, n, None, None, None, None, None) for k, n in PARENTS] + LEAVES
    for i, spec in enumerate(ordered, start=1):
        key_to_id[spec[0]] = f"TASK-{i:03d}"

    # Phase parents (cycle_time/baseline null, no deps).
    for key, name in PARENTS:
        project.tasks.append(Task(
            id=key_to_id[key], name=name, completion_location="DAL",
            calendar_mode="working_days", cycle_time_days=None, parent_id=None,
        ))

    # Leaves, with parent_id and dependencies resolved by key. The dependency-less
    # root task is anchored with a manual_start_date (the program start), exactly as
    # the kickoff task is anchored in the existing demo files.
    for key, name, loc, mode, cycle, parent, deps in LEAVES:
        project.tasks.append(Task(
            id=key_to_id[key], name=name, completion_location=loc,
            calendar_mode=mode, cycle_time_days=cycle,
            manual_start_date=date.fromisoformat(PROGRAM_START) if not deps else None,
            parent_id=key_to_id[parent] if parent else None,
            dependencies=[
                Dependency(id=key_to_id[dk], type=dt, lag_days=lag)
                for dk, dt, lag in deps
            ],
        ))

    settings.next_task_id = len(project.tasks) + 1

    # Engine-authored baseline: schedule, then snapshot computed dates as the plan.
    api.validate_project(project)
    api.set_project_baseline(project, overwrite=True)

    # Make it lifelike: complete the early setup tasks, with one real manual delay.
    api.mark_task_complete(project, key_to_id["kickoff"], completion_date=date(2026, 8, 3))
    api.apply_manual_delay(project, key_to_id["reqs"], 3,
                           reason="Spec freeze slipped pending customer input",
                           today=date(2026, 8, 21))
    api.mark_task_complete(project, key_to_id["reqs"], completion_date=date(2026, 8, 24))
    api.mark_task_complete(project, key_to_id["dplan"], completion_date=date(2026, 9, 3))

    return project


def main() -> int:
    project = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    api.save_project(project, OUT)

    # Report what we produced.
    schedule = api.schedule_project(project)
    end = max(s.effective_finish for s in schedule.values())
    start = min(s.computed_start for s in schedule.values())
    locs = sorted({t.completion_location for t in project.tasks})
    deptypes = sorted({d.type for t in project.tasks for d in t.dependencies})
    completed = sum(1 for t in project.tasks if t.is_complete)
    print(f"Wrote {OUT.relative_to(ROOT)}")
    print(f"  tasks       : {len(project.tasks)} "
          f"({len(PARENTS)} phase parents + {len(LEAVES)} leaves)")
    print(f"  span        : {start} -> {end}  ({(end - start).days} days)")
    print(f"  locations   : {', '.join(locs)}")
    print(f"  dep types   : {', '.join(deptypes)}")
    print(f"  completed   : {completed} (with delay_log on the slipped spec freeze)")
    print(f"  holiday locs: {len(project.settings.holidays)} "
          f"({sum(len(v) for v in project.settings.holidays.values())} entries, "
          f"{YEAR_START}-{YEAR_END})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
