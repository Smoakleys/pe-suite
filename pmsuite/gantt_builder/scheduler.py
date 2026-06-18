"""Forward-pass scheduling.

Computes earliest start and earliest finish for every task, respecting:
- Per-task calendar mode (working_days vs e_days)
- Manual start date as floor
- Full FS / SS / FF / SF dependency types with lag (positive or negative)
- Parent manual starts and parent dependencies as inherited floors
- Dependencies on parent tasks via their rolled-up descendant schedule
- Parent rollup (parent.start = earliest child start; parent.end = latest child end)
- Cumulative delay_days applied to compute effective_finish
- Completion freeze (actual_completion_date overrides computed_finish)

Dependency type semantics (lag values are counted in the predecessor's calendar):
- FS: successor.start >= predecessor.effective_finish + 1 + lag
- SS: successor.start >= predecessor.computed_start + lag
- FF: successor.finish >= predecessor.effective_finish + lag
       => successor.start >= (that finish) - (cycle - 1) in successor's calendar
- SF: successor.finish >= predecessor.computed_start + lag
       => successor.start >= (that finish) - (cycle - 1) in successor's calendar

Backward pass for critical path / float lives in critical_path.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .errors import StructuralError
from .locations import weekday_code
from .logging_config import get_logger
from .models import Project, Task

_log = get_logger(__name__)


@dataclass
class ScheduledTask:
    """Computed schedule data for one task."""

    task_id: str
    computed_start: date
    computed_finish: date
    effective_finish: date  # computed_finish + delay_days, or actual_completion_date if complete


def run_schedule(project: Project) -> dict[str, ScheduledTask]:
    """Compute start / finish / effective_finish for every task.

    Returns a dict keyed by task ID. Includes both leaf tasks and parent rollups.
    """
    schedule: dict[str, ScheduledTask] = {}

    # Compute leaves first in topological order
    leaves = [t for t in project.tasks if not project.has_subtasks(t.id)]
    ordered_leaves = _topological_order(leaves, project)

    for task in ordered_leaves:
        scheduled = _schedule_leaf(task, project, schedule)
        schedule[task.id] = scheduled

    # Roll up parents (any task that has children)
    parents = [t for t in project.tasks if project.has_subtasks(t.id)]
    # Parents may have parents themselves; iterate until stable
    while True:
        progress = False
        for parent in parents:
            if parent.id in schedule:
                continue
            children = project.children_of(parent.id)
            if all(c.id in schedule for c in children):
                child_schedules = [schedule[c.id] for c in children]
                start = min(s.computed_start for s in child_schedules)
                finish = max(s.computed_finish for s in child_schedules)
                effective = max(s.effective_finish for s in child_schedules)
                schedule[parent.id] = ScheduledTask(
                    task_id=parent.id,
                    computed_start=start,
                    computed_finish=finish,
                    effective_finish=effective,
                )
                progress = True
        if not progress:
            break

    _log.info("Scheduled %d tasks for project %s", len(schedule), project.project.id)
    return schedule


def _schedule_leaf(task: Task, project: Project, scheduled: dict[str, ScheduledTask]) -> ScheduledTask:
    """Compute start/finish for a leaf task."""
    if task.cycle_time_days is None or task.cycle_time_days < 1:
        raise StructuralError(f"Leaf task {task.id} has invalid cycle_time_days")

    # Determine floors (max of this task's floor plus all inherited parent floors).
    floors: list[date] = []

    for floor_owner in _task_and_ancestors(task, project):
        if floor_owner.manual_start_date is not None:
            floors.append(floor_owner.manual_start_date)

        for dep in floor_owner.dependencies:
            pred = _dependency_schedule(dep.id, project, scheduled)
            if pred is None:
                raise StructuralError(
                    f"Task {task.id} depends on unscheduled predecessor {dep.id}"
                )
            floor = _dependency_start_floor(task, dep, pred, project)
            floors.append(floor)

    if not floors:
        raise StructuralError(f"Task {task.id} has no anchor (unanchored)")

    raw_start = max(floors)
    computed_start = _snap_to_working_day(raw_start, task, project)
    computed_finish = _compute_finish(task, computed_start, project)

    # Effective finish: completion freezes; otherwise computed + delay_days
    if task.is_complete and task.actual_completion_date is not None:
        effective_finish = task.actual_completion_date
    else:
        effective_finish = _add_days_in_calendar(
            computed_finish, task.delay_days, task.calendar_mode, task.completion_location, project,
        )

    return ScheduledTask(
        task_id=task.id,
        computed_start=computed_start,
        computed_finish=computed_finish,
        effective_finish=effective_finish,
    )


def _compute_finish(task: Task, start: date, project: Project) -> date:
    """Compute finish date for a leaf task starting on `start`. Inclusive cycle time."""
    return _add_days_in_calendar(
        start, task.cycle_time_days - 1, task.calendar_mode, task.completion_location, project,
    )


def _dependency_start_floor(
    task: Task, dep, pred: ScheduledTask, project: Project,
) -> date:
    """Compute the earliest start for `task` implied by one dependency on `pred`.

    Each dependency type produces a floor on the successor's start; the caller
    takes max() across all dependency floors (and manual_start_date / parent floors).
    """
    cycle = task.cycle_time_days or 1
    lag = dep.lag_days
    dep_type = dep.type
    pred_task = project.task_by_id(dep.id)

    if dep_type == "FS":
        # Successor starts the day after predecessor's effective finish + lag.
        base = pred.effective_finish + timedelta(days=1)
        return _apply_lag(base, lag, pred_task, project)

    if dep_type == "SS":
        # Successor starts when predecessor starts (+ lag).
        return _apply_lag(pred.computed_start, lag, pred_task, project)

    if dep_type == "FF":
        # Successor finishes when predecessor finishes (+ lag).
        # => successor.start = implied_finish - (cycle - 1) in successor's calendar
        implied_finish = _apply_lag(pred.effective_finish, lag, pred_task, project)
        return _subtract_days_in_calendar(
            implied_finish, cycle - 1, task.calendar_mode, task.completion_location, project,
        )

    if dep_type == "SF":
        # Successor finishes when predecessor starts (+ lag). Rare.
        implied_finish = _apply_lag(pred.computed_start, lag, pred_task, project)
        return _subtract_days_in_calendar(
            implied_finish, cycle - 1, task.calendar_mode, task.completion_location, project,
        )

    # Unknown type — defensive fallback to FS
    base = pred.effective_finish + timedelta(days=1)
    return _apply_lag(base, lag, pred_task, project)


def _apply_lag(anchor: date, lag_days: int, pred_task: Task | None, project: Project) -> date:
    """Apply dependency lag in the predecessor's calendar mode.

    The anchor is the dependency event date after any fixed day-resolution offset
    has been applied. For example, FS uses predecessor finish + one calendar day
    as its zero-lag anchor, then applies lag from there.
    """
    if lag_days == 0:
        return anchor

    if pred_task is None:
        return anchor + timedelta(days=lag_days)

    if lag_days > 0:
        return _add_days_in_calendar(
            anchor,
            lag_days,
            pred_task.calendar_mode,
            pred_task.completion_location,
            project,
        )

    return _subtract_days_in_calendar(
        anchor,
        abs(lag_days),
        pred_task.calendar_mode,
        pred_task.completion_location,
        project,
    )


def _remove_lag(anchor: date, lag_days: int, pred_task: Task | None, project: Project) -> date:
    """Inverse of _apply_lag, used by the backward CPM pass."""
    if lag_days == 0:
        return anchor

    if pred_task is None:
        return anchor - timedelta(days=lag_days)

    if lag_days > 0:
        return _subtract_days_in_calendar(
            anchor,
            lag_days,
            pred_task.calendar_mode,
            pred_task.completion_location,
            project,
        )

    return _add_days_in_calendar(
        anchor,
        abs(lag_days),
        pred_task.calendar_mode,
        pred_task.completion_location,
        project,
    )


def _snap_to_working_day(d: date, task: Task, project: Project) -> date:
    """Snap a date forward to the next valid working day if the task is working-mode.

    Per DESIGN.md Q3 ("successor calendar mode governs at boundaries"): if the
    successor is a working-day task, its start must land on a working day of its
    own location's calendar. E-day tasks ignore this — they run every calendar day.
    """
    if task.calendar_mode != "working_days":
        return d
    work_week = set(project.settings.work_weeks.get(task.completion_location, []))
    holiday_dates = {h.date for h in project.settings.holidays.get(task.completion_location, [])}
    current = d
    safety = 0
    while (weekday_code(current) not in work_week or current in holiday_dates) and safety < 366:
        current += timedelta(days=1)
        safety += 1
    return current


def _add_days_in_calendar(
    start: date, days_to_add: int, calendar_mode: str, location: str, project: Project,
) -> date:
    """Add `days_to_add` days to `start` according to calendar mode and location."""
    if days_to_add <= 0:
        return start

    if calendar_mode == "e_days":
        return start + timedelta(days=days_to_add)

    # working_days: count forward, skipping non-working days and holidays
    work_week = set(project.settings.work_weeks.get(location, []))
    holiday_dates = {h.date for h in project.settings.holidays.get(location, [])}

    current = start
    remaining = days_to_add
    while remaining > 0:
        current += timedelta(days=1)
        if weekday_code(current) in work_week and current not in holiday_dates:
            remaining -= 1
    return current


def _subtract_days_in_calendar(
    end: date, days_to_subtract: int, calendar_mode: str, location: str, project: Project,
) -> date:
    """Symmetric inverse of _add_days_in_calendar: walk backward from `end`."""
    if days_to_subtract <= 0:
        return end

    if calendar_mode == "e_days":
        return end - timedelta(days=days_to_subtract)

    work_week = set(project.settings.work_weeks.get(location, []))
    holiday_dates = {h.date for h in project.settings.holidays.get(location, [])}

    current = end
    remaining = days_to_subtract
    while remaining > 0:
        current -= timedelta(days=1)
        if weekday_code(current) in work_week and current not in holiday_dates:
            remaining -= 1
    return current


def _topological_order(leaves: list[Task], project: Project) -> list[Task]:
    """Return leaves in topological order so each task's dependencies are scheduled first.

    Parent task dependencies are inherited by descendant leaves. A dependency on
    a parent predecessor expands to that parent's descendant leaves so the
    predecessor rollup can be computed before the successor leaf is scheduled.
    """
    leaf_ids = {t.id for t in leaves}
    leaf_by_id = {t.id: t for t in leaves}
    in_degree: dict[str, int] = {t.id: 0 for t in leaves}
    outgoing: dict[str, list[str]] = {t.id: [] for t in leaves}

    for t in leaves:
        for dep_id in _expanded_leaf_dependency_ids(t, project):
            if dep_id in leaf_ids:
                in_degree[t.id] += 1
                outgoing[dep_id].append(t.id)

    queue = [t for t in leaves if in_degree[t.id] == 0]
    ordered: list[Task] = []
    while queue:
        task = queue.pop(0)
        ordered.append(task)
        for other_id in outgoing.get(task.id, []):
            in_degree[other_id] -= 1
            if in_degree[other_id] == 0:
                queue.append(leaf_by_id[other_id])

    if len(ordered) < len(leaves):
        # Cycle detected; return whatever we have. Validation catches this separately.
        ordered.extend(t for t in leaves if t not in ordered)
    return ordered


def _task_and_ancestors(task: Task, project: Project) -> list[Task]:
    """Return task followed by parent, grandparent, etc. Stops defensively on cycles."""
    result = [task]
    seen = {task.id}
    current = task
    while current.parent_id:
        parent = project.task_by_id(current.parent_id)
        if parent is None or parent.id in seen:
            break
        result.append(parent)
        seen.add(parent.id)
        current = parent
    return result


def _expanded_leaf_dependency_ids(task: Task, project: Project) -> set[str]:
    """Leaf predecessor IDs needed before `task` can be scheduled."""
    result: set[str] = set()
    for floor_owner in _task_and_ancestors(task, project):
        for dep in floor_owner.dependencies:
            pred_task = project.task_by_id(dep.id)
            if pred_task is None:
                continue
            if project.has_subtasks(pred_task.id):
                result.update(project.all_descendant_leaf_ids(pred_task.id))
            else:
                result.add(pred_task.id)

    result.discard(task.id)
    return result


def _dependency_schedule(
    task_id: str,
    project: Project,
    scheduled: dict[str, ScheduledTask],
) -> ScheduledTask | None:
    """Return a scheduled predecessor, computing a transient parent rollup if needed."""
    if task_id in scheduled:
        return scheduled[task_id]

    task = project.task_by_id(task_id)
    if task is None or not project.has_subtasks(task_id):
        return None

    descendant_leaf_ids = project.all_descendant_leaf_ids(task_id)
    if not descendant_leaf_ids:
        return None
    if any(leaf_id not in scheduled for leaf_id in descendant_leaf_ids):
        return None

    descendant_schedules = [scheduled[leaf_id] for leaf_id in descendant_leaf_ids]
    return ScheduledTask(
        task_id=task_id,
        computed_start=min(s.computed_start for s in descendant_schedules),
        computed_finish=max(s.computed_finish for s in descendant_schedules),
        effective_finish=max(s.effective_finish for s in descendant_schedules),
    )
