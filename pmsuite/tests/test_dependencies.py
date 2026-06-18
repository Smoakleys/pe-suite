"""Tests for the four dependency types (FS / SS / FF / SF) with lag.

Each test sets up a minimal two-task project, runs the scheduler, and asserts
the resulting computed_start and computed_finish dates match the documented
semantics in [DESIGN.md §8] and [JSONFILE.md].

All tasks use e_days mode unless otherwise noted, so calendar math is simple
day arithmetic with no work-week or holiday interference.
"""

from __future__ import annotations

from datetime import date, datetime

from gantt_builder.models import (
    Dependency,
    Project,
    ProjectMeta,
    Settings,
    Task,
)
from gantt_builder.scheduler import run_schedule


def _project(tasks: list[Task]) -> Project:
    return Project(
        project=ProjectMeta(
            id="DEPS-TEST",
            name="Deps test",
            timezone="America/Chicago",
            created_at=datetime(2026, 5, 13, 12, 0, 0),
            updated_at=datetime(2026, 5, 13, 12, 0, 0),
        ),
        settings=Settings(
            holidays={"DAL": []},
            work_weeks={"DAL": ["MON", "TUE", "WED", "THU", "FRI"]},
            next_task_id=len(tasks) + 1,
        ),
        tasks=tasks,
    )


def _t(task_id: str, cycle: int, manual_start: date | None = None,
       deps: list[Dependency] | None = None,
       calendar_mode: str = "e_days",
       parent_id: str | None = None) -> Task:
    return Task(
        id=task_id,
        name=task_id,
        completion_location="DAL",
        calendar_mode=calendar_mode,
        cycle_time_days=cycle,
        manual_start_date=manual_start,
        dependencies=deps or [],
        parent_id=parent_id,
    )


def _parent(task_id: str, manual_start: date | None = None,
            deps: list[Dependency] | None = None) -> Task:
    return Task(
        id=task_id,
        name=task_id,
        completion_location="DAL",
        calendar_mode="e_days",
        cycle_time_days=None,
        manual_start_date=manual_start,
        dependencies=deps or [],
    )


# -- FS (default) ----------------------------------------------------------

def test_fs_zero_lag_starts_day_after_predecessor_finishes():
    project = _project([
        _t("TASK-001", cycle=3, manual_start=date(2026, 5, 18)),
        _t("TASK-002", cycle=2, deps=[Dependency(id="TASK-001", type="FS", lag_days=0)]),
    ])
    schedule = run_schedule(project)

    # A: 5/18, 5/19, 5/20 (Mon, Tue, Wed)
    assert schedule["TASK-001"].computed_start == date(2026, 5, 18)
    assert schedule["TASK-001"].computed_finish == date(2026, 5, 20)
    # B: starts day after A finishes
    assert schedule["TASK-002"].computed_start == date(2026, 5, 21)
    assert schedule["TASK-002"].computed_finish == date(2026, 5, 22)


def test_fs_positive_lag_shifts_successor_forward():
    project = _project([
        _t("TASK-001", cycle=1, manual_start=date(2026, 5, 18)),
        _t("TASK-002", cycle=2, deps=[Dependency(id="TASK-001", type="FS", lag_days=3)]),
    ])
    schedule = run_schedule(project)
    # A finishes 5/18. With +3 lag, B starts 5/18 + 1 + 3 = 5/22
    assert schedule["TASK-002"].computed_start == date(2026, 5, 22)


def test_fs_negative_lag_pulls_successor_earlier():
    project = _project([
        _t("TASK-001", cycle=5, manual_start=date(2026, 5, 18)),
        _t("TASK-002", cycle=2, deps=[Dependency(id="TASK-001", type="FS", lag_days=-2)]),
    ])
    schedule = run_schedule(project)
    # A finishes 5/22. With -2 lag, B starts 5/22 + 1 - 2 = 5/21
    assert schedule["TASK-001"].computed_finish == date(2026, 5, 22)
    assert schedule["TASK-002"].computed_start == date(2026, 5, 21)


# -- SS (start-to-start) ---------------------------------------------------

def test_ss_zero_lag_starts_same_day_as_predecessor():
    project = _project([
        _t("TASK-001", cycle=5, manual_start=date(2026, 5, 18)),
        _t("TASK-002", cycle=3, deps=[Dependency(id="TASK-001", type="SS", lag_days=0)]),
    ])
    schedule = run_schedule(project)
    # Both start on 5/18; A finishes 5/22 (5 days), B finishes 5/20 (3 days)
    assert schedule["TASK-001"].computed_start == date(2026, 5, 18)
    assert schedule["TASK-002"].computed_start == date(2026, 5, 18)


def test_ss_positive_lag_starts_n_days_after_predecessor_start():
    project = _project([
        _t("TASK-001", cycle=10, manual_start=date(2026, 5, 18)),
        _t("TASK-002", cycle=2, deps=[Dependency(id="TASK-001", type="SS", lag_days=4)]),
    ])
    schedule = run_schedule(project)
    # B starts 4 days after A starts: 5/18 + 4 = 5/22
    assert schedule["TASK-002"].computed_start == date(2026, 5, 22)


# -- FF (finish-to-finish) -------------------------------------------------

def test_ff_zero_lag_finishes_same_day_as_predecessor():
    project = _project([
        _t("TASK-001", cycle=5, manual_start=date(2026, 5, 18)),
        _t("TASK-002", cycle=2, deps=[Dependency(id="TASK-001", type="FF", lag_days=0)]),
    ])
    schedule = run_schedule(project)
    # A finishes 5/22. B (cycle 2) finishes 5/22 too, so B starts 5/21.
    assert schedule["TASK-001"].computed_finish == date(2026, 5, 22)
    assert schedule["TASK-002"].computed_finish == date(2026, 5, 22)
    assert schedule["TASK-002"].computed_start == date(2026, 5, 21)


def test_ff_positive_lag_finishes_n_days_after_predecessor_finish():
    project = _project([
        _t("TASK-001", cycle=3, manual_start=date(2026, 5, 18)),
        _t("TASK-002", cycle=1, deps=[Dependency(id="TASK-001", type="FF", lag_days=2)]),
    ])
    schedule = run_schedule(project)
    # A finishes 5/20. With +2 lag, B finishes 5/22. B is 1 day, so starts 5/22.
    assert schedule["TASK-001"].computed_finish == date(2026, 5, 20)
    assert schedule["TASK-002"].computed_finish == date(2026, 5, 22)
    assert schedule["TASK-002"].computed_start == date(2026, 5, 22)


# -- SF (start-to-finish) --------------------------------------------------

def test_sf_zero_lag_finishes_when_predecessor_starts():
    project = _project([
        _t("TASK-001", cycle=5, manual_start=date(2026, 5, 18)),
        _t("TASK-002", cycle=3, deps=[Dependency(id="TASK-001", type="SF", lag_days=0)]),
    ])
    schedule = run_schedule(project)
    # A starts 5/18. B finishes 5/18; B is 3 days, so starts 5/16 (2 days earlier).
    # Yes — SF allows successor to start before predecessor (rare but intentional).
    assert schedule["TASK-002"].computed_finish == date(2026, 5, 18)
    assert schedule["TASK-002"].computed_start == date(2026, 5, 16)


def test_sf_positive_lag_finishes_n_days_after_predecessor_start():
    project = _project([
        _t("TASK-001", cycle=5, manual_start=date(2026, 5, 18)),
        _t("TASK-002", cycle=2, deps=[Dependency(id="TASK-001", type="SF", lag_days=3)]),
    ])
    schedule = run_schedule(project)
    # A starts 5/18. +3 lag → B finishes 5/21. B is 2 days, so starts 5/20.
    assert schedule["TASK-002"].computed_finish == date(2026, 5, 21)
    assert schedule["TASK-002"].computed_start == date(2026, 5, 20)


# -- Manual-start-date interaction with all dep types ---------------------

def test_manual_start_acts_as_floor_when_later_than_ss_dep():
    project = _project([
        _t("TASK-001", cycle=5, manual_start=date(2026, 5, 18)),
        _t("TASK-002", cycle=2,
           manual_start=date(2026, 5, 25),  # later than SS-derived floor
           deps=[Dependency(id="TASK-001", type="SS", lag_days=0)]),
    ])
    schedule = run_schedule(project)
    # SS would put B at 5/18; manual_start floor is 5/25 → 5/25 wins.
    assert schedule["TASK-002"].computed_start == date(2026, 5, 25)


# -- Working-day calendar with SS ------------------------------------------

def test_ss_with_working_day_successor_snaps_to_working_day():
    """SS with lag landing on weekend gets snapped to next working day."""
    project = _project([
        # A starts on a Wednesday
        _t("TASK-001", cycle=10, manual_start=date(2026, 5, 20)),
        # B is working_days with SS+lag=3 → would land on Saturday 5/23
        _t("TASK-002", cycle=2,
           calendar_mode="working_days",
           deps=[Dependency(id="TASK-001", type="SS", lag_days=3)]),
    ])
    schedule = run_schedule(project)
    # 5/20 (Wed) + 3 = Sat 5/23 → snap forward to Mon 5/25
    assert schedule["TASK-002"].computed_start == date(2026, 5, 25)


# -- Mixed dependency types in one task -----------------------------------

def test_task_with_mixed_dependency_types_takes_max_floor():
    project = _project([
        _t("TASK-001", cycle=3, manual_start=date(2026, 5, 18)),  # finishes 5/20
        _t("TASK-002", cycle=5, manual_start=date(2026, 5, 18)),  # finishes 5/22
        # C has both: FS on A (would start 5/21) and SS on B (would start 5/18 + 0 = 5/18)
        # FS-on-A floor > SS-on-B floor, so 5/21 wins.
        _t("TASK-003", cycle=1, deps=[
            Dependency(id="TASK-001", type="FS", lag_days=0),
            Dependency(id="TASK-002", type="SS", lag_days=0),
        ]),
    ])
    schedule = run_schedule(project)
    assert schedule["TASK-003"].computed_start == date(2026, 5, 21)


# -- Parent-aware scheduling ----------------------------------------------

def test_parent_manual_start_is_inherited_by_descendant_leaf():
    project = _project([
        _parent("TASK-001", manual_start=date(2026, 5, 20)),
        _t("TASK-002", cycle=1, manual_start=date(2026, 5, 18), parent_id="TASK-001"),
    ])
    schedule = run_schedule(project)

    assert schedule["TASK-002"].computed_start == date(2026, 5, 20)
    assert schedule["TASK-001"].computed_start == date(2026, 5, 20)


def test_parent_dependency_is_inherited_by_descendant_leaf():
    project = _project([
        _t("TASK-001", cycle=2, manual_start=date(2026, 5, 18)),
        _parent("TASK-002", deps=[Dependency(id="TASK-001", type="FS", lag_days=0)]),
        _t("TASK-003", cycle=1, manual_start=date(2026, 5, 18), parent_id="TASK-002"),
    ])
    schedule = run_schedule(project)

    # TASK-001 finishes 5/19, so the parent gate pushes its child to 5/20.
    assert schedule["TASK-003"].computed_start == date(2026, 5, 20)
    assert schedule["TASK-002"].computed_start == date(2026, 5, 20)


def test_leaf_dependency_on_parent_uses_parent_rollup_finish():
    project = _project([
        _parent("TASK-001"),
        _t("TASK-002", cycle=2, manual_start=date(2026, 5, 18), parent_id="TASK-001"),
        _t("TASK-003", cycle=4, manual_start=date(2026, 5, 18), parent_id="TASK-001"),
        _t("TASK-004", cycle=1, deps=[Dependency(id="TASK-001", type="FS", lag_days=0)]),
    ])
    schedule = run_schedule(project)

    assert schedule["TASK-001"].effective_finish == date(2026, 5, 21)
    assert schedule["TASK-004"].computed_start == date(2026, 5, 22)


def test_positive_lag_counts_in_predecessor_calendar():
    project = _project([
        _t("TASK-001", cycle=1, manual_start=date(2026, 5, 20), calendar_mode="working_days"),
        _t("TASK-002", cycle=1, deps=[Dependency(id="TASK-001", type="FS", lag_days=3)]),
    ])
    schedule = run_schedule(project)

    # TASK-001 finishes Wed 5/20. FS zero-lag anchor is Thu 5/21.
    # Three predecessor working days after that are Fri 5/22, Mon 5/25, Tue 5/26.
    assert schedule["TASK-002"].computed_start == date(2026, 5, 26)
