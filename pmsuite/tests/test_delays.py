"""Tests for the delay propagation engine: manual delays, auto-catchup
(per-task accurate, Option B), undo, fresh-project baseline, and completion
freeze.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from gantt_builder import api
from gantt_builder.delays import (
    apply_auto_catchup,
    apply_manual_delay,
    is_auto_catchup_pending,
    preview_auto_catchup,
    undo_delay_batch,
)
from gantt_builder.errors import (
    CompletedTaskCannotBeDelayedError,
    TaskNotFoundError,
)
from gantt_builder.models import (
    Dependency,
    Project,
    ProjectMeta,
    Settings,
    Task,
)
from gantt_builder.scheduler import run_schedule


def _project(tasks: list[Task], last_run: date | None = None) -> Project:
    return Project(
        project=ProjectMeta(
            id="DELAYS-TEST",
            name="Delays test",
            timezone="America/Chicago",
            created_at=datetime(2026, 5, 13, 12, 0, 0),
            updated_at=datetime(2026, 5, 13, 12, 0, 0),
        ),
        settings=Settings(
            holidays={"DAL": []},
            work_weeks={"DAL": ["MON", "TUE", "WED", "THU", "FRI"]},
            next_task_id=len(tasks) + 1,
            last_auto_delay_run=last_run,
        ),
        tasks=tasks,
    )


def _task(task_id: str, cycle: int, start: date | None = None,
          deps: list[str] | None = None,
          is_complete: bool = False,
          completion: date | None = None,
          delay_days: int = 0) -> Task:
    return Task(
        id=task_id,
        name=task_id,
        completion_location="DAL",
        calendar_mode="e_days",
        cycle_time_days=cycle,
        manual_start_date=start,
        dependencies=[Dependency(id=d) for d in (deps or [])],
        is_complete=is_complete,
        actual_completion_date=completion,
        delay_days=delay_days,
    )


# -- Manual delays ---------------------------------------------------------

def test_manual_delay_increments_cumulative_delay_days():
    project = _project([
        _task("TASK-001", cycle=3, start=date(2026, 5, 18)),
    ], last_run=date(2026, 5, 13))

    result = apply_manual_delay(project, "TASK-001", 2, reason="vendor late",
                                 today=date(2026, 5, 14))

    task = project.task_by_id("TASK-001")
    assert task.delay_days == 2
    assert len(task.delay_log) == 1
    assert task.delay_log[0].source == "manual"
    assert task.delay_log[0].days_added == 2
    assert task.delay_log[0].reason == "vendor late"
    assert result.was_applied
    assert result.entries[0].task_id == "TASK-001"
    assert result.entries[0].days_added == 2


def test_manual_delay_compounds():
    project = _project([
        _task("TASK-001", cycle=3, start=date(2026, 5, 18), delay_days=1),
    ], last_run=date(2026, 5, 13))

    apply_manual_delay(project, "TASK-001", 2, today=date(2026, 5, 14))

    task = project.task_by_id("TASK-001")
    assert task.delay_days == 3  # 1 (initial) + 2 (manual)


def test_manual_delay_on_completed_task_raises():
    project = _project([
        _task("TASK-001", cycle=3, start=date(2026, 5, 18),
              is_complete=True, completion=date(2026, 5, 20)),
    ], last_run=date(2026, 5, 13))

    with pytest.raises(CompletedTaskCannotBeDelayedError):
        apply_manual_delay(project, "TASK-001", 2)


def test_manual_delay_on_unknown_task_raises():
    project = _project([
        _task("TASK-001", cycle=3, start=date(2026, 5, 18)),
    ], last_run=date(2026, 5, 13))

    with pytest.raises(TaskNotFoundError):
        apply_manual_delay(project, "TASK-NOPE", 2)


def test_manual_delay_zero_or_negative_rejected():
    project = _project([
        _task("TASK-001", cycle=3, start=date(2026, 5, 18)),
    ], last_run=date(2026, 5, 13))

    with pytest.raises(ValueError):
        apply_manual_delay(project, "TASK-001", 0)
    with pytest.raises(ValueError):
        apply_manual_delay(project, "TASK-001", -1)


# -- Auto-catchup (Option B per-task accurate) ----------------------------

def test_auto_catchup_baseline_on_fresh_project():
    """First call on a fresh project (last_run=None) sets baseline, applies nothing."""
    project = _project([
        _task("TASK-001", cycle=1, start=date(2026, 5, 1)),  # finished 5/1, today is 5/14
    ], last_run=None)

    result = apply_auto_catchup(project, today=date(2026, 5, 14))

    task = project.task_by_id("TASK-001")
    assert task.delay_days == 0  # NOT applied — baseline only
    assert len(task.delay_log) == 0
    assert not result.was_applied
    assert project.settings.last_auto_delay_run == date(2026, 5, 14)


def test_auto_catchup_applies_overdue_days_to_each_task():
    project = _project([
        # Finishes 5/19; today 5/22 → 3 days overdue
        _task("TASK-001", cycle=2, start=date(2026, 5, 18)),
        # Depends on TASK-001 finishing 5/19, then 1 day → finishes 5/20; today 5/22 → 2 days overdue
        _task("TASK-002", cycle=1, deps=["TASK-001"]),
        # Already complete; should NOT be touched
        _task("TASK-003", cycle=1, start=date(2026, 5, 18),
              is_complete=True, completion=date(2026, 5, 18)),
    ], last_run=date(2026, 5, 14))

    result = apply_auto_catchup(project, today=date(2026, 5, 22))

    assert result.was_applied
    task1 = project.task_by_id("TASK-001")
    task2 = project.task_by_id("TASK-002")
    task3 = project.task_by_id("TASK-003")

    # TASK-001 was 3 days overdue
    assert task1.delay_days == 3
    assert task1.delay_log[-1].source == "auto"
    assert task1.delay_log[-1].days_added == 3

    # TASK-002 was 2 days overdue (its own gap, NOT inflated by TASK-001's)
    assert task2.delay_days == 2

    # TASK-003 was complete; should not have been touched
    assert task3.delay_days == 0
    assert len(task3.delay_log) == 0


def test_auto_catchup_skips_when_nothing_overdue():
    project = _project([
        # finishes today — not overdue
        _task("TASK-001", cycle=1, start=date(2026, 5, 22)),
    ], last_run=date(2026, 5, 14))

    result = apply_auto_catchup(project, today=date(2026, 5, 22))

    assert not result.was_applied
    assert project.task_by_id("TASK-001").delay_days == 0


def test_auto_catchup_advances_last_run_even_when_no_delays_applied():
    project = _project([
        _task("TASK-001", cycle=1, start=date(2026, 5, 22)),
    ], last_run=date(2026, 5, 14))

    apply_auto_catchup(project, today=date(2026, 5, 22))
    assert project.settings.last_auto_delay_run == date(2026, 5, 22)


def test_auto_catchup_idempotent_within_same_day():
    project = _project([
        _task("TASK-001", cycle=1, start=date(2026, 5, 18)),
    ], last_run=date(2026, 5, 14))

    # First call: 3 days overdue (5/18 → 5/21)
    apply_auto_catchup(project, today=date(2026, 5, 21))
    delay_after_first = project.task_by_id("TASK-001").delay_days

    # Second call same day: should add nothing (effective_finish now == today)
    apply_auto_catchup(project, today=date(2026, 5, 21))
    delay_after_second = project.task_by_id("TASK-001").delay_days

    assert delay_after_first == delay_after_second
    assert delay_after_first == 3


def test_auto_catchup_then_next_day_adds_one_more():
    project = _project([
        _task("TASK-001", cycle=1, start=date(2026, 5, 18)),
    ], last_run=date(2026, 5, 14))

    apply_auto_catchup(project, today=date(2026, 5, 21))   # +3
    apply_auto_catchup(project, today=date(2026, 5, 22))   # +1

    assert project.task_by_id("TASK-001").delay_days == 4


def test_auto_catchup_does_not_inflate_downstream():
    """Spec rule 9e: each task's delay_days grows from its OWN overdue gap,
    never inflated by the upstream's overdue days cascading down.
    """
    project = _project([
        # cycle=1, start 5/18, e-day → finishes 5/18; today 5/24 → 6 days overdue
        _task("TASK-001", cycle=1, start=date(2026, 5, 18)),
        # depends on TASK-001 (finish 5/18), so starts 5/19, cycle=3 → finishes 5/21
        # today 5/24 → own gap is 3 days overdue (NOT 6+3=9)
        _task("TASK-002", cycle=3, deps=["TASK-001"]),
    ], last_run=date(2026, 5, 17))

    apply_auto_catchup(project, today=date(2026, 5, 24))

    assert project.task_by_id("TASK-001").delay_days == 6
    # Downstream adds only its OWN overdue gap (3), not 6 + cascade
    assert project.task_by_id("TASK-002").delay_days == 3


# -- Undo ------------------------------------------------------------------

def test_undo_manual_delay_within_session():
    project = _project([
        _task("TASK-001", cycle=3, start=date(2026, 5, 18)),
    ], last_run=date(2026, 5, 13))

    result = apply_manual_delay(project, "TASK-001", 4, today=date(2026, 5, 14))
    reverted = undo_delay_batch(project, result)

    assert reverted == ["TASK-001"]
    task = project.task_by_id("TASK-001")
    assert task.delay_days == 0
    assert task.delay_log == []


def test_undo_auto_catchup_batch_within_session():
    project = _project([
        _task("TASK-001", cycle=1, start=date(2026, 5, 18)),
        _task("TASK-002", cycle=1, deps=["TASK-001"]),
    ], last_run=date(2026, 5, 14))

    result = apply_auto_catchup(project, today=date(2026, 5, 24))
    assert len(result.entries) == 2

    reverted = undo_delay_batch(project, result)
    assert set(reverted) == {"TASK-001", "TASK-002"}

    for tid in ("TASK-001", "TASK-002"):
        task = project.task_by_id(tid)
        assert task.delay_days == 0
        assert task.delay_log == []


def test_undo_skips_tasks_with_manually_edited_log():
    """If user edits the log between apply and undo, that task is skipped (safety)."""
    project = _project([
        _task("TASK-001", cycle=1, start=date(2026, 5, 18)),
        _task("TASK-002", cycle=1, start=date(2026, 5, 18)),
    ], last_run=date(2026, 5, 14))

    result = apply_auto_catchup(project, today=date(2026, 5, 21))

    # User "manually" edits TASK-001's log — removes the auto entry
    project.task_by_id("TASK-001").delay_log.clear()

    reverted = undo_delay_batch(project, result)
    assert "TASK-001" not in reverted   # skipped — log entry already gone
    assert "TASK-002" in reverted       # reverted normally


# -- Pending detector ------------------------------------------------------

def test_is_pending_false_for_fresh_project():
    project = _project([_task("TASK-001", cycle=1, start=date(2026, 5, 18))], last_run=None)
    assert not is_auto_catchup_pending(project, today=date(2026, 5, 20))


def test_is_pending_false_when_already_run_today():
    project = _project([_task("TASK-001", cycle=1, start=date(2026, 5, 18))],
                       last_run=date(2026, 5, 22))
    assert not is_auto_catchup_pending(project, today=date(2026, 5, 22))


def test_is_pending_true_when_days_have_passed():
    project = _project([_task("TASK-001", cycle=1, start=date(2026, 5, 18))],
                       last_run=date(2026, 5, 15))
    assert is_auto_catchup_pending(project, today=date(2026, 5, 22))


# -- Public API surface ---------------------------------------------------

def test_api_module_exposes_delay_functions():
    assert hasattr(api, "preview_auto_catchup")
    assert hasattr(api, "apply_auto_catchup")
    assert hasattr(api, "apply_manual_delay")
    assert hasattr(api, "undo_delay_batch")
    assert hasattr(api, "is_auto_catchup_pending")
