"""Two-tier project validation.

Tier 1 (structural — handled at load time in project_io.py): malformed JSON,
missing required fields. Fails fast.

Tier 2 (logical — handled here): circular dependencies, missing references,
duplicate IDs, self-dependencies, invalid parent relationships, unanchored tasks,
invalid cycle times / dates / completion / location / delays. Collects all errors
and raises ValidationFailure with the full list.

Warnings (non-fatal): collected separately and returned alongside any failure.
"""

from __future__ import annotations

from .errors import (
    CircularDependencyError,
    DuplicateTaskIdError,
    GanttError,
    InvalidCompletionDateError,
    InvalidCycleTimeError,
    InvalidDelayDaysError,
    InvalidLocationError,
    InvalidParentRelationshipError,
    MissingDependencyError,
    MissingHolidayDataError,
    ParentHasCycleTimeError,
    SelfDependencyError,
    UnanchoredTaskError,
    ValidationFailure,
)
from .locations import LOCATIONS
from .logging_config import get_logger
from .models import Project, Task

_log = get_logger(__name__)


def validate_project(project: Project) -> list[str]:
    """Run all logical-tier validators on a project.

    Returns a list of warning strings. Raises ValidationFailure if any error is found.
    """
    errors: list[GanttError] = []
    warnings: list[str] = []

    _validate_task_ids_unique(project, errors)
    _validate_locations(project, errors)
    _validate_holiday_data(project, errors)
    _validate_self_dependencies(project, errors)
    _validate_missing_dependencies(project, errors)
    _validate_circular_dependencies(project, errors)
    _validate_expanded_leaf_dependency_cycles(project, errors)
    _validate_parent_relationships(project, errors)
    _validate_cycle_times(project, errors, warnings)
    _validate_anchoring(project, errors)
    _validate_completion(project, errors)
    _validate_delay_days(project, errors)

    _log.info(
        "Validated project %s: %d errors, %d warnings",
        project.project.id, len(errors), len(warnings),
    )

    if errors:
        raise ValidationFailure(errors)

    return warnings


def _validate_task_ids_unique(project: Project, errors: list[GanttError]) -> None:
    seen: dict[str, int] = {}
    for t in project.tasks:
        seen[t.id] = seen.get(t.id, 0) + 1
    duplicates = [tid for tid, n in seen.items() if n > 1]
    for tid in duplicates:
        errors.append(DuplicateTaskIdError(
            f"Task ID '{tid}' appears more than once.",
            affected_tasks=[tid],
        ))


def _validate_locations(project: Project, errors: list[GanttError]) -> None:
    for t in project.tasks:
        if t.completion_location not in LOCATIONS:
            errors.append(InvalidLocationError(
                f"Task '{t.id}' has unknown completion_location '{t.completion_location}'. "
                f"Allowed: {', '.join(LOCATIONS)}.",
                affected_tasks=[t.id],
            ))


def _validate_holiday_data(project: Project, errors: list[GanttError]) -> None:
    referenced_locations = {t.completion_location for t in project.tasks if t.completion_location in LOCATIONS}
    for loc in referenced_locations:
        if loc not in project.settings.holidays:
            errors.append(MissingHolidayDataError(
                f"settings.holidays is missing an entry for location '{loc}'.",
            ))
        if loc not in project.settings.work_weeks:
            errors.append(MissingHolidayDataError(
                f"settings.work_weeks is missing an entry for location '{loc}'.",
            ))


def _validate_self_dependencies(project: Project, errors: list[GanttError]) -> None:
    for t in project.tasks:
        for dep in t.dependencies:
            if dep.id == t.id:
                errors.append(SelfDependencyError(
                    f"Task '{t.id}' depends on itself.",
                    affected_tasks=[t.id],
                ))


def _validate_missing_dependencies(project: Project, errors: list[GanttError]) -> None:
    valid_ids = {t.id for t in project.tasks}
    for t in project.tasks:
        for dep in t.dependencies:
            if dep.id not in valid_ids:
                errors.append(MissingDependencyError(
                    f"Task '{t.id}' depends on unknown task '{dep.id}'.",
                    affected_tasks=[t.id],
                ))


def _validate_circular_dependencies(project: Project, errors: list[GanttError]) -> None:
    graph = {t.id: [d.id for d in t.dependencies] for t in project.tasks}
    visited: dict[str, int] = {}  # 0 = unvisited, 1 = visiting, 2 = done
    cycles: list[list[str]] = []

    def dfs(node: str, path: list[str]) -> None:
        state = visited.get(node, 0)
        if state == 1:
            cycle_start = path.index(node)
            cycles.append(path[cycle_start:] + [node])
            return
        if state == 2:
            return
        visited[node] = 1
        for neighbor in graph.get(node, []):
            dfs(neighbor, path + [node])
        visited[node] = 2

    for tid in graph:
        if visited.get(tid, 0) == 0:
            dfs(tid, [])

    for cycle in cycles:
        errors.append(CircularDependencyError(
            f"Circular dependency detected: {' -> '.join(cycle)}.",
            affected_tasks=cycle,
        ))


def _validate_expanded_leaf_dependency_cycles(project: Project, errors: list[GanttError]) -> None:
    """Detect cycles after parent dependencies are inherited by descendant leaves."""
    leaves = [t for t in project.tasks if not project.has_subtasks(t.id)]
    leaf_ids = {t.id for t in leaves}
    graph: dict[str, list[str]] = {t.id: [] for t in leaves}

    for task in leaves:
        for owner in [task] + [project.task_by_id(a) for a in _ancestor_ids(project, task)]:
            if owner is None:
                continue
            for dep in owner.dependencies:
                pred = project.task_by_id(dep.id)
                if pred is None:
                    continue
                if project.has_subtasks(pred.id):
                    graph[task.id].extend(
                        leaf_id for leaf_id in project.all_descendant_leaf_ids(pred.id)
                        if leaf_id in leaf_ids and leaf_id != task.id
                    )
                elif pred.id in leaf_ids and pred.id != task.id:
                    graph[task.id].append(pred.id)

    visited: dict[str, int] = {}
    cycles: list[list[str]] = []

    def dfs(node: str, path: list[str]) -> None:
        state = visited.get(node, 0)
        if state == 1:
            cycle_start = path.index(node)
            cycles.append(path[cycle_start:] + [node])
            return
        if state == 2:
            return
        visited[node] = 1
        for neighbor in graph.get(node, []):
            dfs(neighbor, path + [node])
        visited[node] = 2

    for tid in graph:
        if visited.get(tid, 0) == 0:
            dfs(tid, [])

    reported: set[frozenset[str]] = set()
    for cycle in cycles:
        key = frozenset(cycle)
        if key in reported:
            continue
        reported.add(key)
        errors.append(CircularDependencyError(
            f"Parent-expanded dependency cycle detected: {' -> '.join(cycle)}.",
            affected_tasks=cycle,
        ))


def _validate_parent_relationships(project: Project, errors: list[GanttError]) -> None:
    valid_ids = {t.id for t in project.tasks}
    for t in project.tasks:
        if t.parent_id is not None and t.parent_id not in valid_ids:
            errors.append(InvalidParentRelationshipError(
                f"Task '{t.id}' references unknown parent_id '{t.parent_id}'.",
                affected_tasks=[t.id],
            ))
        if t.parent_id == t.id:
            errors.append(InvalidParentRelationshipError(
                f"Task '{t.id}' has itself as parent_id.",
                affected_tasks=[t.id],
            ))

    _validate_parent_cycles(project, errors)
    _validate_parent_dependency_cycles(project, errors)


def _validate_parent_cycles(project: Project, errors: list[GanttError]) -> None:
    """Detect indirect parent loops such as A.parent=B and B.parent=A."""
    reported: set[frozenset[str]] = set()

    for task in project.tasks:
        path: list[str] = []
        seen: set[str] = set()
        current: Task | None = task

        while current and current.parent_id:
            if current.id in seen:
                cycle_start = path.index(current.id) if current.id in path else 0
                cycle = path[cycle_start:] + [current.id]
                key = frozenset(cycle)
                if key not in reported:
                    reported.add(key)
                    errors.append(InvalidParentRelationshipError(
                        f"Parent cycle detected: {' -> '.join(cycle)}.",
                        affected_tasks=cycle,
                    ))
                break

            seen.add(current.id)
            path.append(current.id)
            current = project.task_by_id(current.parent_id)


def _validate_parent_dependency_cycles(project: Project, errors: list[GanttError]) -> None:
    """Reject dependencies that would fight the parent/descendant rollup graph."""
    for task in project.tasks:
        descendants = set(project.all_descendant_ids(task.id))
        ancestors = set(_ancestor_ids(project, task))

        for dep in task.dependencies:
            if dep.id in descendants:
                errors.append(InvalidParentRelationshipError(
                    f"Task '{task.id}' depends on descendant '{dep.id}', which creates "
                    "an invalid parent/dependency cycle.",
                    affected_tasks=[task.id, dep.id],
                ))
            if dep.id in ancestors:
                errors.append(InvalidParentRelationshipError(
                    f"Task '{task.id}' depends on ancestor '{dep.id}', which creates "
                    "an invalid parent/dependency cycle.",
                    affected_tasks=[task.id, dep.id],
                ))


def _ancestor_ids(project: Project, task: Task) -> list[str]:
    result: list[str] = []
    seen: set[str] = {task.id}
    current = task
    while current.parent_id:
        if current.parent_id in seen:
            break
        parent = project.task_by_id(current.parent_id)
        if parent is None:
            break
        result.append(parent.id)
        seen.add(parent.id)
        current = parent
    return result


def _validate_cycle_times(project: Project, errors: list[GanttError], warnings: list[str]) -> None:
    for t in project.tasks:
        is_parent = project.has_subtasks(t.id)
        if is_parent:
            if t.cycle_time_days is not None:
                errors.append(ParentHasCycleTimeError(
                    f"Parent task '{t.id}' must not have cycle_time_days set "
                    f"(parent duration is derived from children).",
                    affected_tasks=[t.id],
                ))
        else:
            if t.cycle_time_days is None or t.cycle_time_days < 1:
                errors.append(InvalidCycleTimeError(
                    f"Leaf task '{t.id}' must have cycle_time_days >= 1.",
                    affected_tasks=[t.id],
                ))


def _validate_anchoring(project: Project, errors: list[GanttError]) -> None:
    """A leaf task with no dependencies AND no manual_start_date is unanchored."""
    for t in project.tasks:
        if project.has_subtasks(t.id):
            continue
        if not t.dependencies and t.manual_start_date is None:
            errors.append(UnanchoredTaskError(
                f"Task '{t.id}' has no dependencies and no manual_start_date. "
                f"Every leaf task must be anchored somehow.",
                affected_tasks=[t.id],
            ))


def _validate_completion(project: Project, errors: list[GanttError]) -> None:
    for t in project.tasks:
        if t.is_complete and t.actual_completion_date is None:
            errors.append(InvalidCompletionDateError(
                f"Task '{t.id}' is marked complete but has no actual_completion_date.",
                affected_tasks=[t.id],
            ))
        if (not t.is_complete) and t.actual_completion_date is not None:
            errors.append(InvalidCompletionDateError(
                f"Task '{t.id}' has actual_completion_date set but is_complete is False.",
                affected_tasks=[t.id],
            ))


def _validate_delay_days(project: Project, errors: list[GanttError]) -> None:
    for t in project.tasks:
        if t.delay_days < 0:
            errors.append(InvalidDelayDaysError(
                f"Task '{t.id}' has negative delay_days ({t.delay_days}).",
                affected_tasks=[t.id],
            ))
