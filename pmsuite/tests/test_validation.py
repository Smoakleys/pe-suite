"""Targeted validation tests for production-readiness edge cases."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from gantt_builder.errors import ValidationFailure
from gantt_builder.models import Dependency, Project, ProjectMeta, Settings, Task
from gantt_builder.validation import validate_project


def _project(tasks: list[Task]) -> Project:
    return Project(
        project=ProjectMeta(
            id="VALIDATION-TEST",
            name="Validation test",
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


def _task(task_id: str, *, parent_id: str | None = None,
          deps: list[Dependency] | None = None,
          cycle_time_days: int | None = 1) -> Task:
    return Task(
        id=task_id,
        name=task_id,
        completion_location="DAL",
        calendar_mode="e_days",
        cycle_time_days=cycle_time_days,
        manual_start_date=date(2026, 5, 18) if cycle_time_days is not None else None,
        parent_id=parent_id,
        dependencies=deps or [],
    )


def test_indirect_parent_cycle_is_invalid():
    project = _project([
        _task("TASK-001", parent_id="TASK-002", cycle_time_days=None),
        _task("TASK-002", parent_id="TASK-001", cycle_time_days=None),
    ])

    with pytest.raises(ValidationFailure) as excinfo:
        validate_project(project)

    assert any(err.error_code == "INVALID_PARENT_RELATIONSHIP" for err in excinfo.value.errors)


def test_task_cannot_depend_on_ancestor():
    project = _project([
        _task("TASK-001", cycle_time_days=None),
        _task("TASK-002", parent_id="TASK-001", deps=[Dependency(id="TASK-001")]),
    ])

    with pytest.raises(ValidationFailure) as excinfo:
        validate_project(project)

    assert any("depends on ancestor" in err.message for err in excinfo.value.errors)


def test_parent_cannot_depend_on_descendant():
    project = _project([
        _task("TASK-001", cycle_time_days=None, deps=[Dependency(id="TASK-002")]),
        _task("TASK-002", parent_id="TASK-001"),
    ])

    with pytest.raises(ValidationFailure) as excinfo:
        validate_project(project)

    assert any("depends on descendant" in err.message for err in excinfo.value.errors)


def test_parent_expanded_dependency_cycle_is_invalid():
    project = _project([
        _task("TASK-001", cycle_time_days=None),
        _task("TASK-002", parent_id="TASK-001", deps=[Dependency(id="TASK-003")]),
        _task("TASK-003", cycle_time_days=None),
        _task("TASK-004", parent_id="TASK-003", deps=[Dependency(id="TASK-001")]),
    ])

    with pytest.raises(ValidationFailure) as excinfo:
        validate_project(project)

    assert any(
        err.error_code == "CIRCULAR_DEPENDENCY"
        and "Parent-expanded" in err.message
        for err in excinfo.value.errors
    )
