"""Derived views: pure functions that turn a LoadedProject into UI-ready rows.

These return plain dataclasses, never pydantic models or engine objects. That is the
boundary: panes render `TaskRow` / `PriorityItem` and stay ignorant of the engine.

Everything here is a pure function of the LoadedProject snapshot (including its
`today`), so the same input always yields the same output — trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from .projects import LoadedProject


class TaskStatus(str, Enum):
    """Schedule status of a task relative to the project's "today"."""

    COMPLETE = "complete"
    OVERDUE = "overdue"          # not complete and its finish is in the past
    IN_PROGRESS = "in_progress"  # today falls within [start, finish]
    DUE_SOON = "due_soon"        # starts within DUE_SOON_DAYS
    UPCOMING = "upcoming"        # starts later than that
    UNSCHEDULED = "unscheduled"  # no computed dates (e.g. missing cycle time)


DUE_SOON_DAYS = 7


@dataclass(frozen=True)
class TaskRow:
    """One row in the Tasks pane (hierarchical, declaration-ordered)."""

    id: str
    name: str
    depth: int
    parent_id: str | None
    is_parent: bool
    is_complete: bool
    is_critical: bool
    status: TaskStatus
    start: date | None
    finish: date | None
    location: str | None


@dataclass(frozen=True)
class PriorityItem:
    """One ranked entry in the Priorities pane (critical-path long pole)."""

    rank: int
    task_id: str
    name: str
    status: TaskStatus
    start: date | None
    finish: date | None
    days_overdue: int       # >0 only when status is OVERDUE, else 0
    days_until_start: int    # >0 only when the task hasn't started yet, else 0
    total_float: int


def _status_for(
    loaded: LoadedProject,
    task_id: str,
    is_complete: bool,
) -> TaskStatus:
    if is_complete:
        return TaskStatus.COMPLETE

    sched = loaded.schedule.get(task_id)
    if sched is None:
        return TaskStatus.UNSCHEDULED

    today = loaded.today
    start = sched.computed_start
    finish = sched.effective_finish

    if finish < today:
        return TaskStatus.OVERDUE
    if start <= today <= finish:
        return TaskStatus.IN_PROGRESS
    if (start - today).days <= DUE_SOON_DAYS:
        return TaskStatus.DUE_SOON
    return TaskStatus.UPCOMING


def task_rows(loaded: LoadedProject) -> list[TaskRow]:
    """Flatten the task hierarchy into ordered rows with depth, for the Tasks pane.

    Children follow their parent (depth-first), preserving the JSON's declaration
    order at each level — the same order an engineer authored in the editor.
    """
    project = loaded.project

    # Build an ordered children map from the task list so ordering is explicit and
    # independent of any engine helper's iteration order.
    children: dict[str | None, list] = {}
    for task in project.tasks:
        children.setdefault(task.parent_id, []).append(task)

    rows: list[TaskRow] = []

    def walk(parent_id: str | None, depth: int) -> None:
        for task in children.get(parent_id, []):
            is_parent = project.has_subtasks(task.id)
            sched = loaded.schedule.get(task.id)
            rows.append(
                TaskRow(
                    id=task.id,
                    name=task.name,
                    depth=depth,
                    parent_id=task.parent_id,
                    is_parent=is_parent,
                    is_complete=task.is_complete,
                    is_critical=task.id in loaded.critical.critical_task_ids,
                    status=_status_for(loaded, task.id, task.is_complete),
                    start=sched.computed_start if sched else None,
                    finish=sched.effective_finish if sched else None,
                    location=task.completion_location,
                )
            )
            walk(task.id, depth + 1)

    walk(None, 0)
    return rows


def priorities(loaded: LoadedProject, limit: int | None = None) -> list[PriorityItem]:
    """Rank the actionable critical-path tasks for the Priorities pane.

    Actionable = a leaf task (not a parent rollup) that is on the critical-path long
    pole and not yet complete. These are ordered by when they need to happen
    (earliest start, then earliest finish, then least float) and numbered from 1.
    """
    project = loaded.project
    critical_ids = loaded.critical.critical_task_ids
    today = loaded.today

    candidates = [
        t for t in project.tasks
        if t.id in critical_ids
        and not project.has_subtasks(t.id)   # leaves only — actionable items
        and not t.is_complete
    ]

    def sort_key(task):
        sched = loaded.schedule.get(task.id)
        # Unscheduled tasks sort last (date.max), but stay in the list.
        start = sched.computed_start if sched else date.max
        finish = sched.effective_finish if sched else date.max
        return (start, finish, loaded.critical.total_float.get(task.id, 0))

    candidates.sort(key=sort_key)
    if limit is not None:
        candidates = candidates[:limit]

    items: list[PriorityItem] = []
    for rank, task in enumerate(candidates, start=1):
        sched = loaded.schedule.get(task.id)
        start = sched.computed_start if sched else None
        finish = sched.effective_finish if sched else None
        status = _status_for(loaded, task.id, task.is_complete)

        days_overdue = max(0, (today - finish).days) if (finish and finish < today) else 0
        days_until_start = max(0, (start - today).days) if (start and start > today) else 0

        items.append(
            PriorityItem(
                rank=rank,
                task_id=task.id,
                name=task.name,
                status=status,
                start=start,
                finish=finish,
                days_overdue=days_overdue,
                days_until_start=days_until_start,
                total_float=loaded.critical.total_float.get(task.id, 0),
            )
        )
    return items
