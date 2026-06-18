"""Project mutation helpers used by the Streamlit editing surface."""

from __future__ import annotations

from typing import Any

from .errors import (
    InvalidParentRelationshipError,
    SelfDependencyError,
    TaskDeletionBlockedError,
    TaskNotFoundError,
)
from .locations import LOCATIONS
from .models import Dependency, Project, Task


def add_task(project: Project, **kwargs: Any) -> Task:
    """Append a new task with the next stable TASK-NNN identifier."""
    if "id" in kwargs:
        raise ValueError("Task IDs are system-generated and cannot be supplied.")

    task_id = _next_task_id(project)
    defaults = {
        "id": task_id,
        "name": "New task",
        "completion_location": _default_location(project),
        "calendar_mode": "working_days",
        "cycle_time_days": 1,
        "manual_start_date": None,
    }
    task = Task.model_validate({**defaults, **kwargs})
    project.tasks.append(task)
    return task


def update_task(project: Project, task_id: str, **kwargs: Any) -> Task:
    """Replace one task after validating the updated model fields."""
    if "id" in kwargs and kwargs["id"] != task_id:
        raise ValueError("Task IDs are stable and cannot be changed.")

    idx, task = _task_index(project, task_id)
    payload = task.model_dump(mode="python", exclude_defaults=False, exclude_none=False)
    payload.update(kwargs)
    payload["id"] = task_id
    updated = Task.model_validate(payload)
    project.tasks[idx] = updated
    return updated


def delete_task(project: Project, task_id: str) -> None:
    """Delete a task when no dependencies or children still reference it."""
    idx, _task = _task_index(project, task_id)

    dependents = sorted(
        task.id
        for task in project.tasks
        if any(dep.id == task_id for dep in task.dependencies)
    )
    if dependents:
        raise TaskDeletionBlockedError(
            f"Cannot delete '{task_id}'; other tasks depend on it.",
            affected_tasks=[task_id, *dependents],
        )

    children = sorted(task.id for task in project.tasks if task.parent_id == task_id)
    if children:
        raise TaskDeletionBlockedError(
            f"Cannot delete '{task_id}'; it has child tasks.",
            affected_tasks=[task_id, *children],
        )

    del project.tasks[idx]


def add_dependency(
    project: Project,
    task_id: str,
    dep_id: str,
    type: str = "FS",
    lag_days: int = 0,
) -> None:
    """Add or update a dependency on a task."""
    _idx, task = _task_index(project, task_id)
    if project.task_by_id(dep_id) is None:
        raise TaskNotFoundError(
            f"Cannot add dependency: unknown predecessor '{dep_id}'.",
            affected_tasks=[task_id, dep_id],
        )
    if task_id == dep_id:
        raise SelfDependencyError(
            f"Task '{task_id}' cannot depend on itself.",
            affected_tasks=[task_id],
        )
    if dep_id in project.all_descendant_ids(task_id) or task_id in project.all_descendant_ids(dep_id):
        raise InvalidParentRelationshipError(
            f"Dependency between '{task_id}' and '{dep_id}' conflicts with the parent hierarchy.",
            affected_tasks=[task_id, dep_id],
        )

    dep = Dependency.model_validate({"id": dep_id, "type": type, "lag_days": lag_days})
    for i, existing in enumerate(task.dependencies):
        if existing.id == dep_id:
            task.dependencies[i] = dep
            return
    task.dependencies.append(dep)


def remove_dependency(project: Project, task_id: str, dep_id: str) -> None:
    """Remove a dependency from a task. No-op if the dependency is absent."""
    _idx, task = _task_index(project, task_id)
    task.dependencies = [dep for dep in task.dependencies if dep.id != dep_id]


def _next_task_id(project: Project) -> str:
    used = {task.id for task in project.tasks}
    n = max(project.settings.next_task_id, 1)
    while True:
        task_id = f"TASK-{n:03d}"
        n += 1
        if task_id not in used:
            used.add(task_id)
            while f"TASK-{n:03d}" in used:
                n += 1
            project.settings.next_task_id = n
            return task_id


def _default_location(project: Project) -> str:
    for location in project.settings.work_weeks:
        if location in LOCATIONS:
            return location
    return LOCATIONS[0]


def _task_index(project: Project, task_id: str) -> tuple[int, Task]:
    for idx, task in enumerate(project.tasks):
        if task.id == task_id:
            return idx, task
    raise TaskNotFoundError(
        f"Unknown task '{task_id}'.",
        affected_tasks=[task_id],
    )
