"""Tests for the CPM backward pass: total float, critical path detection,
parent inheritance, and completed-task exclusion.
"""

from __future__ import annotations

from datetime import datetime, date

import pytest

from gantt_builder.critical_path import compute_critical_path
from gantt_builder.models import (
    Dependency,
    Project,
    ProjectMeta,
    Settings,
    Task,
)
from gantt_builder.scheduler import run_schedule


def _make_project(tasks: list[Task]) -> Project:
    """Build a minimal valid USA-only project from a list of tasks."""
    return Project(
        project=ProjectMeta(
            id="TEST",
            name="Test Project",
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


def _eday_task(task_id: str, name: str, cycle: int, manual_start: date | None = None,
               deps: list[str] | None = None, parent_id: str | None = None,
               is_complete: bool = False,
               actual_completion: date | None = None) -> Task:
    return Task(
        id=task_id,
        name=name,
        completion_location="DAL",
        calendar_mode="e_days",
        cycle_time_days=cycle,
        manual_start_date=manual_start,
        dependencies=[Dependency(id=d) for d in (deps or [])],
        parent_id=parent_id,
        is_complete=is_complete,
        actual_completion_date=actual_completion,
    )


def _parent_task(task_id: str, name: str, deps: list[str] | None = None) -> Task:
    return Task(
        id=task_id,
        name=name,
        completion_location="DAL",
        calendar_mode="e_days",
        cycle_time_days=None,
        dependencies=[Dependency(id=d) for d in (deps or [])],
    )


def test_empty_project_returns_no_critical():
    project = _make_project([])
    schedule = run_schedule(project)
    result = compute_critical_path(project, schedule)
    assert result.project_end is None
    assert result.critical_task_ids == set()
    assert result.total_float == {}


def test_linear_chain_all_tasks_critical():
    """A → B → C — all three should be on the critical path."""
    project = _make_project([
        _eday_task("TASK-001", "A", cycle=1, manual_start=date(2026, 5, 18)),
        _eday_task("TASK-002", "B", cycle=2, deps=["TASK-001"]),
        _eday_task("TASK-003", "C", cycle=1, deps=["TASK-002"]),
    ])
    schedule = run_schedule(project)
    result = compute_critical_path(project, schedule)

    assert result.critical_task_ids == {"TASK-001", "TASK-002", "TASK-003"}
    assert result.total_float["TASK-001"] == 0
    assert result.total_float["TASK-002"] == 0
    assert result.total_float["TASK-003"] == 0


def test_parallel_diamond_longer_path_is_critical():
    """A → (B[3d] || C[1d]) → D. The B branch is longer; C has 2 days of float."""
    project = _make_project([
        _eday_task("TASK-001", "A", cycle=1, manual_start=date(2026, 5, 18)),
        _eday_task("TASK-002", "B-long",  cycle=3, deps=["TASK-001"]),
        _eday_task("TASK-003", "C-short", cycle=1, deps=["TASK-001"]),
        _eday_task("TASK-004", "D", cycle=1, deps=["TASK-002", "TASK-003"]),
    ])
    schedule = run_schedule(project)
    result = compute_critical_path(project, schedule)

    # A, long B, D on critical; short C has float
    assert "TASK-001" in result.critical_task_ids  # head — on every path
    assert "TASK-002" in result.critical_task_ids  # longer branch
    assert "TASK-004" in result.critical_task_ids  # tail
    assert "TASK-003" not in result.critical_task_ids  # shorter branch has slack

    # C should have 2 days of float (B is 3 days, C is 1 day → 2 days slack)
    assert result.total_float["TASK-003"] == 2
    assert result.total_float["TASK-002"] == 0


def test_completed_task_excluded_from_critical():
    """Even on a strict chain, a completed task is NOT in the live critical set."""
    project = _make_project([
        _eday_task("TASK-001", "A", cycle=1, manual_start=date(2026, 5, 18),
                   is_complete=True, actual_completion=date(2026, 5, 18)),
        _eday_task("TASK-002", "B", cycle=2, deps=["TASK-001"]),
        _eday_task("TASK-003", "C", cycle=1, deps=["TASK-002"]),
    ])
    schedule = run_schedule(project)
    result = compute_critical_path(project, schedule)

    assert "TASK-001" not in result.critical_task_ids  # completed
    assert "TASK-002" in result.critical_task_ids
    assert "TASK-003" in result.critical_task_ids


def test_parent_inherits_critical_from_descendant():
    """A parent whose child is on the critical path is itself marked critical."""
    project = _make_project([
        _eday_task("TASK-001", "Pre", cycle=1, manual_start=date(2026, 5, 18)),
        _parent_task("TASK-002", "Parent"),
        _eday_task("TASK-003", "Child-on-critical", cycle=2, deps=["TASK-001"],
                   parent_id="TASK-002"),
        _eday_task("TASK-004", "Post", cycle=1, deps=["TASK-003"]),
    ])
    schedule = run_schedule(project)
    result = compute_critical_path(project, schedule)

    # The parent should be marked critical because its child is critical
    assert "TASK-003" in result.critical_task_ids  # the actual critical child
    assert "TASK-002" in result.critical_task_ids  # parent inherits


def test_long_pole_includes_dependency_inherited_from_parent():
    """A parent-level dependency should still mark the gating predecessor critical."""
    project = _make_project([
        _eday_task("TASK-001", "Pre", cycle=2, manual_start=date(2026, 5, 18)),
        _parent_task("TASK-002", "Parent", deps=["TASK-001"]),
        _eday_task("TASK-003", "Child", cycle=1, manual_start=date(2026, 5, 18),
                   parent_id="TASK-002"),
    ])
    schedule = run_schedule(project)
    result = compute_critical_path(project, schedule)

    assert schedule["TASK-003"].computed_start == date(2026, 5, 20)
    assert "TASK-001" in result.critical_task_ids
    assert "TASK-002" in result.critical_task_ids
    assert "TASK-003" in result.critical_task_ids


def test_project_end_matches_latest_effective_finish():
    project = _make_project([
        _eday_task("TASK-001", "A", cycle=1, manual_start=date(2026, 5, 18)),
        _eday_task("TASK-002", "B", cycle=3, deps=["TASK-001"]),
    ])
    schedule = run_schedule(project)
    result = compute_critical_path(project, schedule)

    expected_end = max(s.effective_finish for s in schedule.values())
    assert result.project_end == expected_end


def test_total_float_never_negative():
    """A constraint-feasible schedule should never produce negative float."""
    project = _make_project([
        _eday_task("TASK-001", "A", cycle=1, manual_start=date(2026, 5, 18)),
        _eday_task("TASK-002", "B", cycle=2, deps=["TASK-001"]),
        _eday_task("TASK-003", "C", cycle=1, deps=["TASK-001"]),
    ])
    schedule = run_schedule(project)
    result = compute_critical_path(project, schedule)

    for tid, tf in result.total_float.items():
        assert tf >= 0, f"Task {tid} has negative total float {tf}"


def test_critical_path_with_lag():
    """A lagged FS dependency consumes float for non-critical tasks."""
    project = _make_project([
        _eday_task("TASK-001", "A", cycle=1, manual_start=date(2026, 5, 18)),
        _eday_task("TASK-002", "B", cycle=2, deps=["TASK-001"]),
        # C has a +5 day lag — pushes its start far past B; it'll be critical
        Task(
            id="TASK-003", name="C-lagged",
            completion_location="DAL", calendar_mode="e_days",
            cycle_time_days=1,
            dependencies=[Dependency(id="TASK-001", type="FS", lag_days=5)],
        ),
        _eday_task("TASK-004", "D", cycle=1, deps=["TASK-002", "TASK-003"]),
    ])
    schedule = run_schedule(project)
    result = compute_critical_path(project, schedule)

    # C-lagged should be on critical path (its 5-day lag pushes things)
    # Verify by checking C's effective_finish: should match or exceed B's
    c_finish = schedule["TASK-003"].computed_finish
    b_finish = schedule["TASK-002"].computed_finish
    assert c_finish >= b_finish, f"With +5 lag, C should finish at or after B (C={c_finish}, B={b_finish})"
    assert "TASK-003" in result.critical_task_ids
