"""Delay propagation engine and auto-catchup-on-load.

Per DESIGN.md §11 / MASTERECAP.md Q9, Q11, Q24:

- `delay_days` is cumulative, stored on the task. Scheduler adds it to
  `computed_finish` to produce `effective_finish`.
- Both manual user input and the auto-daily-check add to `delay_days`.
- Multi-day catch-up uses Option B (per-task accurate static): for each
  currently overdue task, add `max(0, today - effective_finish)` once.
  Upstream delays do NOT inflate downstream `delay_days` — downstream shifts
  via the dependency cascade only.
- Completion freezes `delay_days` (preserved historically; no longer applied
  because `actual_completion_date` is now truth).
- Every delay application produces a `DelayLogEntry` for audit and undo.
- Fresh project (no prior `last_auto_delay_run`): set baseline to today on
  first auto-catchup call without applying any delays.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .errors import CompletedTaskCannotBeDelayedError, TaskNotFoundError
from .logging_config import get_logger
from .models import DelayLogEntry, Project
from .scheduler import run_schedule

_log = get_logger(__name__)


@dataclass
class DelayApplicationEntry:
    """One task's contribution to a delay batch."""

    task_id: str
    days_added: int


@dataclass
class DelayApplicationResult:
    """Outcome of a delay application — returned by apply_* and passed to undo.

    `entries` is empty when no delays were applied (e.g., nothing overdue,
    or fresh-project baseline initialization).
    """

    applied_date: date
    source: str  # "manual" | "auto"
    reason: str | None
    entries: list[DelayApplicationEntry] = field(default_factory=list)

    @property
    def was_applied(self) -> bool:
        return bool(self.entries)

    @property
    def total_days_added(self) -> int:
        return sum(e.days_added for e in self.entries)


def preview_auto_catchup(project: Project, today: date | None = None) -> DelayApplicationResult:
    """Compute what auto-catchup would do WITHOUT mutating the project.

    Run by the Streamlit UI on load to populate the "Apply auto-catchup" modal
    with the actual counts the user is about to commit to.
    """
    today = today or date.today()
    last_run = project.settings.last_auto_delay_run

    # Fresh project — baseline initialization, no delays preview.
    if last_run is None:
        return DelayApplicationResult(
            applied_date=today,
            source="auto",
            reason="auto-catchup (baseline initialization)",
            entries=[],
        )

    reason = f"auto-catchup since {last_run.isoformat()}"
    schedule = run_schedule(project)

    entries: list[DelayApplicationEntry] = []
    for task in project.tasks:
        if task.is_complete:
            continue
        if project.has_subtasks(task.id):
            continue
        s = schedule.get(task.id)
        if s is None:
            continue
        days_overdue = (today - s.effective_finish).days
        if days_overdue > 0:
            entries.append(DelayApplicationEntry(task_id=task.id, days_added=days_overdue))

    return DelayApplicationResult(
        applied_date=today,
        source="auto",
        reason=reason,
        entries=entries,
    )


def apply_auto_catchup(project: Project, today: date | None = None) -> DelayApplicationResult:
    """Apply auto-catchup delays in-place to the project.

    Mutates each affected leaf task's `delay_days` and appends a `DelayLogEntry`.
    Updates `settings.last_auto_delay_run`. Fresh projects (no prior run) are
    initialized to today without applying any delays.

    Returns the DelayApplicationResult describing what was applied. Pass it to
    `undo_delay_batch` within the session to revert.
    """
    today = today or date.today()
    last_run = project.settings.last_auto_delay_run

    # Fresh-project baseline (Q24e)
    if last_run is None:
        project.settings.last_auto_delay_run = today
        _log.info("Initialized auto-delay baseline to %s for project %s", today, project.project.id)
        return DelayApplicationResult(
            applied_date=today,
            source="auto",
            reason="auto-catchup (baseline initialization)",
            entries=[],
        )

    preview = preview_auto_catchup(project, today=today)

    for entry in preview.entries:
        task = project.task_by_id(entry.task_id)
        if task is None:
            continue
        task.delay_days += entry.days_added
        task.delay_log.append(DelayLogEntry(
            date=today,
            source="auto",
            days_added=entry.days_added,
            reason=preview.reason,
        ))

    project.settings.last_auto_delay_run = today
    _log.info(
        "Auto-catchup applied for project %s: %d tasks, %d total days",
        project.project.id, len(preview.entries), preview.total_days_added,
    )

    return preview


def apply_manual_delay(
    project: Project,
    task_id: str,
    days_added: int,
    reason: str | None = None,
    today: date | None = None,
) -> DelayApplicationResult:
    """Apply a manual delay to one task. Returns the batch result for undo support.

    Raises:
        TaskNotFoundError: if `task_id` is unknown to the project.
        CompletedTaskCannotBeDelayedError: if the task is already complete
            (delays are frozen on completion per Q9c).
        ValueError: if `days_added < 1`.
    """
    today = today or date.today()
    task = project.task_by_id(task_id)
    if task is None:
        raise TaskNotFoundError(
            f"Cannot apply delay: unknown task '{task_id}'.",
            affected_tasks=[task_id],
        )
    if task.is_complete:
        raise CompletedTaskCannotBeDelayedError(
            f"Task '{task_id}' is complete; delays are frozen and cannot be modified.",
            affected_tasks=[task_id],
        )
    if days_added < 1:
        raise ValueError("days_added must be >= 1")

    task.delay_days += days_added
    task.delay_log.append(DelayLogEntry(
        date=today,
        source="manual",
        days_added=days_added,
        reason=reason,
    ))

    _log.info(
        "Manual delay applied to task %s in project %s: +%d days",
        task_id, project.project.id, days_added,
    )

    return DelayApplicationResult(
        applied_date=today,
        source="manual",
        reason=reason,
        entries=[DelayApplicationEntry(task_id=task_id, days_added=days_added)],
    )


def undo_delay_batch(project: Project, batch: DelayApplicationResult) -> list[str]:
    """Reverse a delay batch within the session.

    Returns a list of task IDs successfully reverted. Tasks whose `delay_log`
    no longer contains a matching entry (because the user manually edited it
    in between) are skipped — those task IDs are NOT in the returned list.
    The skip is intentional: don't clobber a user's manual edit (Q24c safety).

    Caller can compare `len(returned) < len(batch.entries)` to detect skips.
    """
    reverted: list[str] = []

    for entry in batch.entries:
        task = project.task_by_id(entry.task_id)
        if task is None:
            continue

        # Find the matching log entry by (date, source, days_added, reason).
        matching_idx = None
        for i in range(len(task.delay_log) - 1, -1, -1):  # search from most recent
            le = task.delay_log[i]
            if (le.date == batch.applied_date
                    and le.source == batch.source
                    and le.days_added == entry.days_added
                    and le.reason == batch.reason):
                matching_idx = i
                break

        if matching_idx is None:
            continue  # already reverted or manually edited away

        del task.delay_log[matching_idx]
        task.delay_days = max(0, task.delay_days - entry.days_added)
        reverted.append(task.id)

    _log.info(
        "Reverted delay batch for project %s: %d of %d entries (date=%s, source=%s)",
        project.project.id, len(reverted), len(batch.entries), batch.applied_date, batch.source,
    )

    return reverted


def is_auto_catchup_pending(project: Project, today: date | None = None) -> bool:
    """True if `apply_auto_catchup` would do something (excluding baseline init).

    The UI uses this to decide whether to show the auto-catchup prompt on load.
    """
    today = today or date.today()
    last_run = project.settings.last_auto_delay_run
    if last_run is None:
        return False
    return today > last_run
