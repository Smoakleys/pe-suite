"""Task completion logic: mark complete, parent cascade, unmark, undo.

Per DESIGN.md §10 / MASTERECAP.md Q8:

- Marking `is_complete: true` requires `actual_completion_date` (defaults to today).
- Completion freezes the task's effective dates — dependents key off
  `actual_completion_date`, not the previously computed finish.
- **Parent completion cascades to all descendants.** Every descendant leaf
  gets `is_complete: true` and `actual_completion_date = parent_date`,
  regardless of cycle times.
- **Exception (Q8d common-sense reading):** descendants whose own
  `actual_completion_date` is EARLIER than the parent's keep their earlier
  date — we don't destroy real history. Descendants completed LATER than
  the parent are overwritten to the parent's date (the parent's completion
  is the authoritative event).
- Unset is supported (`is_complete: true → false` clears the date).
- Manual delay on a completed task is rejected (delays are frozen on
  completion). See `delays.apply_manual_delay`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .errors import TaskNotFoundError
from .logging_config import get_logger
from .models import Project

_log = get_logger(__name__)


@dataclass
class CompletionChange:
    """Audit record of one task's state change during a completion batch."""

    task_id: str
    prev_is_complete: bool
    prev_actual_completion_date: date | None
    new_is_complete: bool
    new_actual_completion_date: date | None


@dataclass
class CompletionResult:
    """Outcome of a mark-complete operation, suitable for undo."""

    primary_task_id: str
    applied_date: date
    changes: list[CompletionChange] = field(default_factory=list)
    preserved: list[str] = field(default_factory=list)
    """Task IDs of descendants kept with their own earlier completion date."""


def mark_task_complete(
    project: Project,
    task_id: str,
    completion_date: date | None = None,
) -> CompletionResult:
    """Mark a task complete. If the task is a parent, cascade to descendants.

    Cascade rule (Q8d):
    - Descendant NOT complete → mark complete with `completion_date`.
    - Descendant complete with EARLIER date → preserve descendant's earlier date.
    - Descendant complete with LATER date → overwrite to `completion_date`.
    - Descendant complete with SAME date → no change recorded.

    Raises:
        TaskNotFoundError: if `task_id` is unknown.
    """
    completion_date = completion_date or date.today()
    task = project.task_by_id(task_id)
    if task is None:
        raise TaskNotFoundError(
            f"Cannot mark complete: unknown task '{task_id}'.",
            affected_tasks=[task_id],
        )

    result = CompletionResult(
        primary_task_id=task_id,
        applied_date=completion_date,
    )

    # Determine affected tasks: the primary + every descendant (leaves and parents).
    affected_ids = [task_id] + project.all_descendant_ids(task_id)

    for tid in affected_ids:
        t = project.task_by_id(tid)
        if t is None:
            continue

        # Skip if already complete with an earlier or same date — preserve history.
        if t.is_complete and t.actual_completion_date is not None:
            if t.actual_completion_date < completion_date:
                result.preserved.append(tid)
                continue
            if t.actual_completion_date == completion_date:
                # Same state — no-op
                continue

        change = CompletionChange(
            task_id=tid,
            prev_is_complete=t.is_complete,
            prev_actual_completion_date=t.actual_completion_date,
            new_is_complete=True,
            new_actual_completion_date=completion_date,
        )
        t.is_complete = True
        t.actual_completion_date = completion_date
        result.changes.append(change)

    _log.info(
        "Mark-complete on %s (project %s): %d changes, %d preserved",
        task_id, project.project.id, len(result.changes), len(result.preserved),
    )

    return result


def unmark_task_complete(project: Project, task_id: str) -> None:
    """Toggle is_complete: true → false on ONE task. Clears actual_completion_date.

    Does NOT cascade to descendants. If the user needs to unmark a cascaded
    batch, they should use `undo_complete_batch` with the original CompletionResult.

    Raises:
        TaskNotFoundError: if `task_id` is unknown.
    """
    task = project.task_by_id(task_id)
    if task is None:
        raise TaskNotFoundError(
            f"Cannot unmark complete: unknown task '{task_id}'.",
            affected_tasks=[task_id],
        )

    task.is_complete = False
    task.actual_completion_date = None
    _log.info("Unmarked task %s in project %s", task_id, project.project.id)


def undo_complete_batch(project: Project, result: CompletionResult) -> list[str]:
    """Reverse a mark-complete batch within the session.

    Each task's state is restored to its `prev_*` snapshot, but only if the
    task's CURRENT state still matches the `new_*` snapshot we wrote
    (defensive: don't clobber subsequent manual edits).

    Returns the list of task IDs whose state was restored.
    """
    reverted: list[str] = []

    for change in result.changes:
        task = project.task_by_id(change.task_id)
        if task is None:
            continue
        if (task.is_complete == change.new_is_complete
                and task.actual_completion_date == change.new_actual_completion_date):
            task.is_complete = change.prev_is_complete
            task.actual_completion_date = change.prev_actual_completion_date
            reverted.append(task.id)

    _log.info(
        "Undid mark-complete batch on %s in project %s: %d of %d restored",
        result.primary_task_id, project.project.id, len(reverted), len(result.changes),
    )

    return reverted
