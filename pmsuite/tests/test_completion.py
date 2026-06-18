"""Tests for the completion engine: mark, unmark, parent cascade, preserved
children, and undo.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from gantt_builder import api
from gantt_builder.completion import (
    mark_task_complete,
    undo_complete_batch,
    unmark_task_complete,
)
from gantt_builder.errors import TaskNotFoundError
from gantt_builder.models import (
    Dependency,
    Project,
    ProjectMeta,
    Settings,
    Task,
)


def _project(tasks: list[Task]) -> Project:
    return Project(
        project=ProjectMeta(
            id="COMP-TEST",
            name="Completion test",
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


def _task(task_id: str, cycle: int | None, start: date | None = None,
          parent_id: str | None = None,
          deps: list[str] | None = None,
          is_complete: bool = False,
          completion: date | None = None) -> Task:
    return Task(
        id=task_id,
        name=task_id,
        completion_location="DAL",
        calendar_mode="e_days",
        cycle_time_days=cycle,
        manual_start_date=start,
        dependencies=[Dependency(id=d) for d in (deps or [])],
        parent_id=parent_id,
        is_complete=is_complete,
        actual_completion_date=completion,
    )


# -- Mark single leaf complete --------------------------------------------

def test_mark_leaf_complete_sets_state():
    project = _project([_task("TASK-001", cycle=3, start=date(2026, 5, 18))])
    result = mark_task_complete(project, "TASK-001", completion_date=date(2026, 5, 20))

    task = project.task_by_id("TASK-001")
    assert task.is_complete is True
    assert task.actual_completion_date == date(2026, 5, 20)
    assert result.primary_task_id == "TASK-001"
    assert len(result.changes) == 1
    assert result.preserved == []


def test_mark_complete_defaults_completion_date_to_today():
    project = _project([_task("TASK-001", cycle=3, start=date(2026, 5, 18))])
    result = mark_task_complete(project, "TASK-001")
    assert result.applied_date == date.today()
    assert project.task_by_id("TASK-001").actual_completion_date == date.today()


def test_mark_complete_on_unknown_task_raises():
    project = _project([_task("TASK-001", cycle=3, start=date(2026, 5, 18))])
    with pytest.raises(TaskNotFoundError):
        mark_task_complete(project, "TASK-NOPE")


def test_mark_complete_idempotent_same_date():
    project = _project([_task("TASK-001", cycle=3, start=date(2026, 5, 18),
                              is_complete=True, completion=date(2026, 5, 20))])
    result = mark_task_complete(project, "TASK-001", completion_date=date(2026, 5, 20))
    assert result.changes == []  # no-op
    # Same-date case isn't counted as preserved either — it's just a no-op
    assert result.preserved == []


# -- Parent cascade --------------------------------------------------------

def test_marking_parent_complete_cascades_to_all_descendants():
    project = _project([
        _task("TASK-001", cycle=None),  # parent
        _task("TASK-002", cycle=2, start=date(2026, 5, 18), parent_id="TASK-001"),
        _task("TASK-003", cycle=3, start=date(2026, 5, 18), parent_id="TASK-001"),
    ])
    result = mark_task_complete(project, "TASK-001", completion_date=date(2026, 5, 22))

    for tid in ("TASK-001", "TASK-002", "TASK-003"):
        task = project.task_by_id(tid)
        assert task.is_complete is True
        assert task.actual_completion_date == date(2026, 5, 22)

    assert {c.task_id for c in result.changes} == {"TASK-001", "TASK-002", "TASK-003"}
    assert result.preserved == []


def test_cascade_preserves_descendant_with_earlier_completion_date():
    """Q8d common-sense reading: a child completed earlier than the parent
    keeps its own earlier date (we don't destroy real history).
    """
    project = _project([
        _task("TASK-001", cycle=None),  # parent
        _task("TASK-002", cycle=2, start=date(2026, 5, 18), parent_id="TASK-001",
              is_complete=True, completion=date(2026, 5, 15)),  # finished earlier
        _task("TASK-003", cycle=3, start=date(2026, 5, 18), parent_id="TASK-001"),
    ])
    result = mark_task_complete(project, "TASK-001", completion_date=date(2026, 5, 22))

    # TASK-002 keeps its earlier date
    assert project.task_by_id("TASK-002").actual_completion_date == date(2026, 5, 15)
    assert "TASK-002" in result.preserved

    # TASK-001 (parent) and TASK-003 get the parent's date
    assert project.task_by_id("TASK-001").actual_completion_date == date(2026, 5, 22)
    assert project.task_by_id("TASK-003").actual_completion_date == date(2026, 5, 22)


def test_cascade_overwrites_descendant_with_later_completion_date():
    """A child marked complete LATER than the parent's date is overwritten —
    the parent's completion is the authoritative event.
    """
    project = _project([
        _task("TASK-001", cycle=None),  # parent
        _task("TASK-002", cycle=2, start=date(2026, 5, 18), parent_id="TASK-001",
              is_complete=True, completion=date(2026, 5, 28)),  # nonsensically later
    ])
    mark_task_complete(project, "TASK-001", completion_date=date(2026, 5, 22))

    # TASK-002's later date is overwritten
    assert project.task_by_id("TASK-002").actual_completion_date == date(2026, 5, 22)


def test_cascade_recurses_through_multi_level_tree():
    project = _project([
        _task("TASK-001", cycle=None),  # grandparent
        _task("TASK-002", cycle=None, parent_id="TASK-001"),  # parent
        _task("TASK-003", cycle=2, start=date(2026, 5, 18), parent_id="TASK-002"),  # leaf
    ])
    mark_task_complete(project, "TASK-001", completion_date=date(2026, 5, 25))

    for tid in ("TASK-001", "TASK-002", "TASK-003"):
        assert project.task_by_id(tid).is_complete is True
        assert project.task_by_id(tid).actual_completion_date == date(2026, 5, 25)


# -- Completion freezes scheduler -----------------------------------------

def test_completed_task_freezes_effective_finish_for_dependents():
    """Once a task is marked complete, its effective_finish becomes
    actual_completion_date — dependents key off the actual finish, not the
    previously computed finish.
    """
    project = _project([
        _task("TASK-001", cycle=5, start=date(2026, 5, 18)),  # would finish 5/22
        _task("TASK-002", cycle=1, deps=["TASK-001"]),
    ])
    # Mark TASK-001 complete EARLY on 5/19 — dependents should pull forward
    mark_task_complete(project, "TASK-001", completion_date=date(2026, 5, 19))

    schedule = api.schedule_project(project)
    # TASK-002 starts day after actual completion, not after computed_finish
    assert schedule["TASK-002"].computed_start == date(2026, 5, 20)


# -- Unmark single task ---------------------------------------------------

def test_unmark_task_clears_completion_state():
    project = _project([
        _task("TASK-001", cycle=3, start=date(2026, 5, 18),
              is_complete=True, completion=date(2026, 5, 20)),
    ])
    unmark_task_complete(project, "TASK-001")

    task = project.task_by_id("TASK-001")
    assert task.is_complete is False
    assert task.actual_completion_date is None


def test_unmark_does_not_cascade():
    """Unmarking a parent does NOT cascade to descendants."""
    project = _project([
        _task("TASK-001", cycle=None,
              is_complete=True, completion=date(2026, 5, 22)),
        _task("TASK-002", cycle=2, start=date(2026, 5, 18), parent_id="TASK-001",
              is_complete=True, completion=date(2026, 5, 22)),
    ])
    unmark_task_complete(project, "TASK-001")

    # Parent unmarked
    assert project.task_by_id("TASK-001").is_complete is False
    # Child STILL complete (no cascade on unmark)
    assert project.task_by_id("TASK-002").is_complete is True


def test_unmark_unknown_task_raises():
    project = _project([_task("TASK-001", cycle=3, start=date(2026, 5, 18))])
    with pytest.raises(TaskNotFoundError):
        unmark_task_complete(project, "TASK-NOPE")


# -- Undo of completion batch ---------------------------------------------

def test_undo_restores_previous_states():
    project = _project([
        _task("TASK-001", cycle=None),  # parent
        _task("TASK-002", cycle=2, start=date(2026, 5, 18), parent_id="TASK-001",
              is_complete=True, completion=date(2026, 5, 15)),  # preserved
        _task("TASK-003", cycle=3, start=date(2026, 5, 18), parent_id="TASK-001"),
    ])
    result = mark_task_complete(project, "TASK-001", completion_date=date(2026, 5, 22))
    assert project.task_by_id("TASK-003").is_complete is True

    reverted = undo_complete_batch(project, result)

    # TASK-001 was newly completed → reverted to incomplete
    assert "TASK-001" in reverted
    assert project.task_by_id("TASK-001").is_complete is False

    # TASK-003 was newly completed → reverted to incomplete
    assert "TASK-003" in reverted
    assert project.task_by_id("TASK-003").is_complete is False
    assert project.task_by_id("TASK-003").actual_completion_date is None

    # TASK-002 was preserved (not in changes) → unchanged, still completed on 5/15
    assert project.task_by_id("TASK-002").is_complete is True
    assert project.task_by_id("TASK-002").actual_completion_date == date(2026, 5, 15)


def test_undo_skips_tasks_whose_state_was_subsequently_edited():
    """If the user changes a task's state between mark_complete and undo,
    that task is skipped to avoid clobbering the manual edit.
    """
    project = _project([
        _task("TASK-001", cycle=2, start=date(2026, 5, 18)),
        _task("TASK-002", cycle=2, start=date(2026, 5, 18)),
    ])
    result = mark_task_complete(project, "TASK-001", completion_date=date(2026, 5, 20))
    # Same batch, mark TASK-002 separately
    result2 = mark_task_complete(project, "TASK-002", completion_date=date(2026, 5, 20))

    # User then changes TASK-001's completion date manually
    project.task_by_id("TASK-001").actual_completion_date = date(2026, 5, 21)

    reverted = undo_complete_batch(project, result)
    assert "TASK-001" not in reverted   # skipped — state diverged
    # TASK-001 keeps its manually edited state
    assert project.task_by_id("TASK-001").actual_completion_date == date(2026, 5, 21)


# -- Public API surface ---------------------------------------------------

def test_api_module_exposes_completion_functions():
    assert hasattr(api, "mark_task_complete")
    assert hasattr(api, "unmark_task_complete")
    assert hasattr(api, "undo_complete_batch")
