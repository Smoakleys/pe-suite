"""Tests for the baseline snapshot operation."""

from __future__ import annotations

from datetime import date, datetime

from gantt_builder import api
from gantt_builder.baseline import set_project_baseline
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
            id="BASELINE-TEST",
            name="Baseline test",
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


def _task(task_id, cycle, start=None, deps=None,
          baseline_start=None, baseline_finish=None) -> Task:
    return Task(
        id=task_id,
        name=task_id,
        completion_location="DAL",
        calendar_mode="e_days",
        cycle_time_days=cycle,
        manual_start_date=start,
        baseline_start=baseline_start,
        baseline_finish=baseline_finish,
        dependencies=[Dependency(id=d) for d in (deps or [])],
    )


def test_set_baseline_populates_from_computed_dates():
    project = _project([
        _task("TASK-001", cycle=3, start=date(2026, 5, 18)),
        _task("TASK-002", cycle=2, deps=["TASK-001"]),
    ])

    result = set_project_baseline(project)

    assert result.count_baselined == 2
    assert set(result.tasks_baselined) == {"TASK-001", "TASK-002"}

    # TASK-001: 5/18, 5/19, 5/20 (e-day cycle=3)
    assert project.task_by_id("TASK-001").baseline_start == date(2026, 5, 18)
    assert project.task_by_id("TASK-001").baseline_finish == date(2026, 5, 20)
    # TASK-002: starts 5/21, cycle=2 -> 5/22
    assert project.task_by_id("TASK-002").baseline_start == date(2026, 5, 21)
    assert project.task_by_id("TASK-002").baseline_finish == date(2026, 5, 22)


def test_set_baseline_skips_already_baselined_tasks_by_default():
    project = _project([
        _task("TASK-001", cycle=3, start=date(2026, 5, 18),
              baseline_start=date(2026, 5, 1), baseline_finish=date(2026, 5, 3)),
        _task("TASK-002", cycle=2, deps=["TASK-001"]),
    ])

    result = set_project_baseline(project)

    # TASK-001 already baselined → skipped, keeps its prior baseline
    assert "TASK-001" in result.tasks_skipped
    assert project.task_by_id("TASK-001").baseline_start == date(2026, 5, 1)
    assert project.task_by_id("TASK-001").baseline_finish == date(2026, 5, 3)

    # TASK-002 was unbaselined → now populated
    assert "TASK-002" in result.tasks_baselined
    assert project.task_by_id("TASK-002").baseline_start == date(2026, 5, 21)


def test_set_baseline_with_overwrite_replaces_existing_values():
    project = _project([
        _task("TASK-001", cycle=3, start=date(2026, 5, 18),
              baseline_start=date(2026, 5, 1), baseline_finish=date(2026, 5, 3)),
    ])

    set_project_baseline(project, overwrite=True)

    assert project.task_by_id("TASK-001").baseline_start == date(2026, 5, 18)
    assert project.task_by_id("TASK-001").baseline_finish == date(2026, 5, 20)


def test_baseline_unchanged_by_subsequent_delays():
    """The baseline is the snapshot — it doesn't move when delays accumulate."""
    project = _project([
        _task("TASK-001", cycle=3, start=date(2026, 5, 18)),
    ])
    set_project_baseline(project)

    # Apply a delay
    api.apply_manual_delay(project, "TASK-001", 5, today=date(2026, 5, 14))

    # Baseline values are unchanged
    assert project.task_by_id("TASK-001").baseline_start == date(2026, 5, 18)
    assert project.task_by_id("TASK-001").baseline_finish == date(2026, 5, 20)
    # But the live schedule reflects the delay
    schedule = api.schedule_project(project)
    assert schedule["TASK-001"].effective_finish == date(2026, 5, 25)


def test_api_module_exposes_set_project_baseline():
    assert hasattr(api, "set_project_baseline")
