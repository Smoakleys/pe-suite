"""Critical-path computation (CPM-style).

Forward + backward pass to compute total float for every task. Tasks with
total_float == 0 are on the critical path. Completed tasks are excluded from
the live critical path (their effective_finish is fixed and they can no longer
slip), but a snapshot is captured to project.history at completion time.

Handles all four dependency types (FS / SS / FF / SF) with lag. The backward
pass derives a maximum allowable LF for each predecessor from each successor's
LS or LF depending on the dependency type:

- FS: pred.LF <= succ.LS - 1 - lag
- SS: pred.LS <= succ.LS - lag   (translated to LF via cycle in pred's calendar)
- FF: pred.LF <= succ.LF - lag
- SF: pred.LS <= succ.LF - lag   (translated to LF via cycle in pred's calendar)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .logging_config import get_logger
from .models import Project, Task
from .scheduler import (
    ScheduledTask,
    _add_days_in_calendar,
    _dependency_schedule,
    _dependency_start_floor,
    _remove_lag,
    _subtract_days_in_calendar,
    _task_and_ancestors,
    _topological_order,
)

_log = get_logger(__name__)


@dataclass
class CriticalPathResult:
    """Result of CPM analysis for a project."""

    project_end: date | None
    critical_task_ids: set[str]
    total_float: dict[str, int]  # task_id -> total float in days
    latest_start: dict[str, date] = field(default_factory=dict)
    latest_finish: dict[str, date] = field(default_factory=dict)


def compute_critical_path(project: Project, schedule: dict[str, ScheduledTask]) -> CriticalPathResult:
    """Compute project end, latest start/finish, total float, and critical tasks.

    Algorithm:
    1. Project end = max effective_finish across all scheduled tasks.
    2. Backward pass over leaves in REVERSE topological order:
       - For each leaf T, LF = min over successors S of (S's LS - 1 - lag),
         or project_end if T has no successors.
       - LS = LF - (cycle_time - 1) in T's calendar mode.
    3. Total float = LS - computed_start (in calendar days).
    4. Critical = (float == 0) AND (not is_complete).
    5. Parent tasks inherit critical status from any critical descendant.
    """
    if not schedule:
        return CriticalPathResult(
            project_end=None, critical_task_ids=set(), total_float={},
        )

    leaves = [t for t in project.tasks if not project.has_subtasks(t.id)]
    leaf_ids = {t.id for t in leaves}

    project_end = max(s.effective_finish for s in schedule.values())

    # Build successors map: task_id -> list of leaf tasks that directly depend on it.
    # Parent-involved dependencies are still represented in the long-pole pass;
    # total_float remains leaf-level diagnostics for direct leaf constraints.
    successors: dict[str, list[Task]] = {tid: [] for tid in leaf_ids}
    for t in leaves:
        for dep in t.dependencies:
            if dep.id in leaf_ids:
                successors[dep.id].append(t)

    # Backward pass in REVERSE topological order
    topo_order = _topological_order(leaves, project)
    latest_finish: dict[str, date] = {}
    latest_start: dict[str, date] = {}

    for task in reversed(topo_order):
        succ_list = successors.get(task.id, [])
        cycle = task.cycle_time_days or 1
        lf_constraints: list[date] = []

        for succ in succ_list:
            for dep in succ.dependencies:
                if dep.id != task.id:
                    continue
                succ_ls = latest_start.get(succ.id)
                succ_lf = latest_finish.get(succ.id)
                if succ_ls is None or succ_lf is None:
                    continue

                pred_task = project.task_by_id(dep.id)
                if dep.type == "FS":
                    # pred.LF <= succ.LS - 1 - lag
                    lag_removed = _remove_lag(succ_ls, dep.lag_days, pred_task, project)
                    lf_constraints.append(lag_removed - timedelta(days=1))
                elif dep.type == "SS":
                    # pred.LS <= succ.LS - lag  =>  pred.LF <= (that) + (cycle - 1) in pred's calendar
                    pred_ls_max = _remove_lag(succ_ls, dep.lag_days, pred_task, project)
                    pred_lf_max = _add_days_in_calendar(
                        pred_ls_max, cycle - 1, task.calendar_mode, task.completion_location, project,
                    )
                    lf_constraints.append(pred_lf_max)
                elif dep.type == "FF":
                    # pred.LF <= succ.LF - lag
                    lf_constraints.append(_remove_lag(succ_lf, dep.lag_days, pred_task, project))
                elif dep.type == "SF":
                    # pred.LS <= succ.LF - lag  =>  pred.LF <= (that) + (cycle - 1)
                    pred_ls_max = _remove_lag(succ_lf, dep.lag_days, pred_task, project)
                    pred_lf_max = _add_days_in_calendar(
                        pred_ls_max, cycle - 1, task.calendar_mode, task.completion_location, project,
                    )
                    lf_constraints.append(pred_lf_max)
                else:
                    # defensive fallback — FS semantics
                    lag_removed = _remove_lag(succ_ls, dep.lag_days, pred_task, project)
                    lf_constraints.append(lag_removed - timedelta(days=1))
                break

        lf = min(lf_constraints) if lf_constraints else project_end
        latest_finish[task.id] = lf

        ls = _subtract_days_in_calendar(
            lf, cycle - 1, task.calendar_mode, task.completion_location, project,
        )
        latest_start[task.id] = ls

    # Total float = LS - computed_start (in calendar days). Reported for diagnostics.
    total_float: dict[str, int] = {}
    for task in leaves:
        s = schedule.get(task.id)
        ls = latest_start.get(task.id)
        if s is None or ls is None:
            total_float[task.id] = 0
            continue
        tf = (ls - s.computed_start).days
        total_float[task.id] = max(0, tf)

    # "Critical" set is the LONG POLE: tasks on the gating chain from project end.
    # Walks back from each terminal leaf, marking the predecessor(s) whose
    # dependency-derived floor is the latest at each step. This is the
    # user-visible "long pole" view (DESIGN.md Q15 / Q33 addendum) — distinct
    # from strict CPM float==0, which working-day boundary snapping can disrupt.
    critical: set[str] = _compute_long_pole(project, schedule)

    # Parents inherit critical status from any critical descendant
    parents = [t for t in project.tasks if project.has_subtasks(t.id)]
    for parent in parents:
        descendants = project.all_descendant_leaf_ids(parent.id)
        if not descendants:
            total_float[parent.id] = 0
            continue
        if any(d in critical for d in descendants):
            total_float[parent.id] = 0
            critical.add(parent.id)
        else:
            descendant_floats = [total_float.get(d, 0) for d in descendants]
            total_float[parent.id] = min(descendant_floats) if descendant_floats else 0

    _log.info(
        "CPM for project %s: end=%s, %d critical tasks, %d leaves analyzed",
        project.project.id, project_end, len(critical), len(leaves),
    )

    return CriticalPathResult(
        project_end=project_end,
        critical_task_ids=critical,
        total_float=total_float,
        latest_start=latest_start,
        latest_finish=latest_finish,
    )


def _compute_long_pole(project: Project, schedule: dict[str, ScheduledTask]) -> set[str]:
    """Identify tasks on the gating chain — the "long pole" view.

    For each task in the project, the GATING predecessor is the one whose
    dependency-derived floor on the successor's start is the latest (the
    one whose finish/start dictates when the successor can begin). The long
    pole is the transitive closure of gating predecessors walking back from
    each terminal leaf.

    Why this exists alongside total_float: strict CPM critical (float==0)
    is mathematically defensible but visually unstable when working-day
    boundary snapping introduces 1-day float bumps. Users tracking the
    "long pole" want a stable, intuitive answer: the chain of tasks that
    drove the project end date.
    """
    if not schedule:
        return set()

    project_end = max(s.effective_finish for s in schedule.values())
    leaf_index = {t.id: t for t in project.tasks if not project.has_subtasks(t.id)}

    long_pole: set[str] = set()
    queue: list[Task] = []

    # Seed with terminal leaves: leaves whose effective_finish equals project_end.
    # Completed tasks excluded (their effective_finish is fixed and they can no longer slip).
    for t in leaf_index.values():
        s = schedule.get(t.id)
        if s and s.effective_finish == project_end and not t.is_complete:
            long_pole.add(t.id)
            queue.append(t)

    visited: set[str] = set()
    while queue:
        task = queue.pop()
        if task.id in visited:
            continue
        visited.add(task.id)

        # Compute the dep-derived floor each predecessor imposes on this task,
        # including dependency floors inherited from ancestor parents.
        floors: list[tuple[str, date, str]] = []
        for floor_owner in _task_and_ancestors(task, project):
            for dep in floor_owner.dependencies:
                pred_sched = _dependency_schedule(dep.id, project, schedule)
                if pred_sched is None:
                    continue
                try:
                    floors.append((
                        dep.id,
                        _dependency_start_floor(task, dep, pred_sched, project),
                        dep.type,
                    ))
                except Exception:
                    continue

        if not floors:
            continue

        max_floor = max(floor for _, floor, _ in floors)
        for pred_id, floor, dep_type in floors:
            if floor == max_floor:
                pred_task = project.task_by_id(pred_id)
                if pred_task is None:
                    continue

                if pred_id in leaf_index:
                    if not pred_task.is_complete:
                        long_pole.add(pred_id)
                        if pred_id not in visited:
                            queue.append(pred_task)
                    continue

                for leaf_id in _gating_leaf_ids_for_parent_dependency(
                    pred_id, dep_type, project, schedule,
                ):
                    leaf_task = leaf_index.get(leaf_id)
                    if leaf_task and not leaf_task.is_complete:
                        long_pole.add(leaf_id)
                        if leaf_id not in visited:
                            queue.append(leaf_task)

    return long_pole


def _gating_leaf_ids_for_parent_dependency(
    parent_id: str,
    dep_type: str,
    project: Project,
    schedule: dict[str, ScheduledTask],
) -> list[str]:
    """Pick descendant leaves that drive a parent predecessor's relevant event."""
    leaf_ids = project.all_descendant_leaf_ids(parent_id)
    scheduled = [(leaf_id, schedule[leaf_id]) for leaf_id in leaf_ids if leaf_id in schedule]
    if not scheduled:
        return []

    if dep_type in {"SS", "SF"}:
        earliest_start = min(s.computed_start for _, s in scheduled)
        return [leaf_id for leaf_id, s in scheduled if s.computed_start == earliest_start]

    latest_finish = max(s.effective_finish for _, s in scheduled)
    return [leaf_id for leaf_id, s in scheduled if s.effective_finish == latest_finish]
