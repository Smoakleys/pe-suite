"""Tests for Step 6 project editing API primitives."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from gantt_builder import api
from gantt_builder.errors import SelfDependencyError, TaskDeletionBlockedError, TaskNotFoundError
from gantt_builder.models import Dependency, Project, ProjectMeta, Settings, Task


def _project(tasks: list[Task], next_task_id: int = 1) -> Project:
    return Project(
        project=ProjectMeta(
            id="EDIT-TEST",
            name="Editing test",
            timezone="America/Chicago",
            created_at=datetime(2026, 5, 13, 12, 0, 0),
            updated_at=datetime(2026, 5, 13, 12, 0, 0),
        ),
        settings=Settings(
            holidays={"DAL": []},
            work_weeks={"DAL": ["MON", "TUE", "WED", "THU", "FRI"]},
            next_task_id=next_task_id,
        ),
        tasks=tasks,
    )


def _task(task_id: str, *, deps: list[Dependency] | None = None,
          parent_id: str | None = None) -> Task:
    return Task(
        id=task_id,
        name=task_id,
        completion_location="DAL",
        calendar_mode="e_days",
        cycle_time_days=1,
        manual_start_date=date(2026, 5, 18),
        dependencies=deps or [],
        parent_id=parent_id,
    )


def test_add_task_generates_next_available_id_and_advances_counter():
    project = _project([_task("TASK-001"), _task("TASK-003")], next_task_id=1)

    task = api.add_task(project, name="Inserted task")

    assert task.id == "TASK-002"
    assert task.name == "Inserted task"
    assert project.settings.next_task_id == 4
    assert project.tasks[-1] is task


def test_update_task_validates_and_replaces_task():
    project = _project([_task("TASK-001")], next_task_id=2)

    task = api.update_task(
        project,
        "TASK-001",
        name="Updated",
        cycle_time_days=3,
        calendar_mode="working_days",
    )

    assert task.name == "Updated"
    assert task.cycle_time_days == 3
    assert project.task_by_id("TASK-001").calendar_mode == "working_days"


def test_update_task_cannot_rename_id():
    project = _project([_task("TASK-001")], next_task_id=2)

    with pytest.raises(ValueError):
        api.update_task(project, "TASK-001", id="TASK-999")


def test_delete_task_removes_unreferenced_task():
    project = _project([_task("TASK-001")], next_task_id=2)

    api.delete_task(project, "TASK-001")

    assert project.tasks == []


def test_delete_task_rejects_dependents():
    project = _project([
        _task("TASK-001"),
        _task("TASK-002", deps=[Dependency(id="TASK-001")]),
    ], next_task_id=3)

    with pytest.raises(TaskDeletionBlockedError) as excinfo:
        api.delete_task(project, "TASK-001")

    assert excinfo.value.affected_tasks == ["TASK-001", "TASK-002"]


def test_delete_task_rejects_parent_with_children():
    project = _project([
        Task(
            id="TASK-001",
            name="Parent",
            completion_location="DAL",
            calendar_mode="e_days",
            cycle_time_days=None,
        ),
        _task("TASK-002", parent_id="TASK-001"),
    ], next_task_id=3)

    with pytest.raises(TaskDeletionBlockedError) as excinfo:
        api.delete_task(project, "TASK-001")

    assert excinfo.value.affected_tasks == ["TASK-001", "TASK-002"]


def test_add_dependency_adds_and_updates_existing_edge():
    project = _project([_task("TASK-001"), _task("TASK-002")], next_task_id=3)

    api.add_dependency(project, "TASK-002", "TASK-001", type="SS", lag_days=2)

    dep = project.task_by_id("TASK-002").dependencies[0]
    assert dep.id == "TASK-001"
    assert dep.type == "SS"
    assert dep.lag_days == 2

    api.add_dependency(project, "TASK-002", "TASK-001", type="FF", lag_days=-1)
    deps = project.task_by_id("TASK-002").dependencies
    assert len(deps) == 1
    assert deps[0].type == "FF"
    assert deps[0].lag_days == -1


def test_add_dependency_rejects_unknown_and_self_dependency():
    project = _project([_task("TASK-001")], next_task_id=2)

    with pytest.raises(TaskNotFoundError):
        api.add_dependency(project, "TASK-001", "TASK-999")
    with pytest.raises(SelfDependencyError):
        api.add_dependency(project, "TASK-001", "TASK-001")


def test_remove_dependency_is_idempotent():
    project = _project([
        _task("TASK-001"),
        _task("TASK-002", deps=[Dependency(id="TASK-001")]),
    ], next_task_id=3)

    api.remove_dependency(project, "TASK-002", "TASK-001")
    api.remove_dependency(project, "TASK-002", "TASK-001")

    assert project.task_by_id("TASK-002").dependencies == []


def test_api_module_exposes_editing_functions():
    for name in ("add_task", "update_task", "delete_task", "add_dependency", "remove_dependency"):
        assert hasattr(api, name)
