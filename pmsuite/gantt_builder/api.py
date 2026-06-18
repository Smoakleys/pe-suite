"""Public API surface for PMSuite Gantt Builder.

This is the module Streamlit (and any other consumer) imports. It wraps the
internal modules and applies validation + scheduling at the right boundaries.

API operations raise GanttError subclasses on failure; callers can serialize
errors to the structured envelope via `.to_envelope()` for UI display.
"""

from __future__ import annotations

from pathlib import Path

from .baseline import set_project_baseline as _set_baseline
from .completion import (
    mark_task_complete as _mark_complete,
    undo_complete_batch as _undo_complete,
    unmark_task_complete as _unmark_complete,
)
from .critical_path import compute_critical_path
from .delays import (
    apply_auto_catchup as _apply_auto_catchup,
    apply_manual_delay as _apply_manual_delay,
    is_auto_catchup_pending as _is_pending,
    preview_auto_catchup as _preview_auto_catchup,
    undo_delay_batch as _undo_delay_batch,
)
from .editing import (
    add_dependency as _add_dependency,
    add_task as _add_task,
    delete_task as _delete_task,
    remove_dependency as _remove_dependency,
    update_task as _update_task,
)
from .excel_builder import build_excel as _build_excel
from .logging_config import get_logger
from .models import LastExport, Project
from .project_io import load_project as _load, save_project as _save
from .scheduler import run_schedule
from .time_utils import project_now
from .validation import validate_project as _validate

_log = get_logger(__name__)


def load_project(path: str | Path) -> Project:
    """Load a project from JSON. Raises StructuralError on parse failure."""
    return _load(path)


def save_project(project: Project, path: str | Path) -> None:
    """Atomically save the project JSON. Updates `project.updated_at`."""
    _save(project, path)


def validate_project(project: Project) -> list[str]:
    """Run logical-tier validation. Raises ValidationFailure if errors exist.

    Returns a list of warning strings (non-fatal). Save / Build operations call
    this internally at appropriate boundaries.
    """
    return _validate(project)


def schedule_project(project: Project):
    """Run the forward pass scheduler. Returns a dict of task_id -> ScheduledTask."""
    return run_schedule(project)


def build_excel(project: Project, output_dir: str | Path | None = None) -> Path:
    """Validate, schedule, and write the Excel workbook. Returns the output path.

    Raises ValidationFailure if logical validation fails (Excel build is gated on
    clean validation per DESIGN.md Q13).
    """
    _validate(project)
    schedule = run_schedule(project)
    critical = compute_critical_path(project, schedule)
    output_path = _build_excel(project, schedule, critical, output_dir=output_dir)

    project.project.last_export = LastExport(
        path=str(output_path),
        at=project_now(project),
    )
    return output_path


# -- Delay engine ----------------------------------------------------------

def preview_auto_catchup(project: Project, today=None):
    """Compute what auto-catchup would do without mutating the project.

    Returns a DelayApplicationResult. UI uses this to populate the
    "Apply auto-catchup?" modal on project load.
    """
    return _preview_auto_catchup(project, today=today)


def apply_auto_catchup(project: Project, today=None):
    """Apply auto-catchup delays in-place. Returns a DelayApplicationResult."""
    return _apply_auto_catchup(project, today=today)


def apply_manual_delay(project: Project, task_id: str, days_added: int,
                       reason: str | None = None, today=None):
    """Apply a manual delay to one task. Returns a DelayApplicationResult."""
    return _apply_manual_delay(project, task_id, days_added, reason=reason, today=today)


def undo_delay_batch(project: Project, batch) -> list[str]:
    """Reverse a delay batch within the session. Returns reverted task IDs."""
    return _undo_delay_batch(project, batch)


def is_auto_catchup_pending(project: Project, today=None) -> bool:
    """True if `apply_auto_catchup` would actually do something."""
    return _is_pending(project, today=today)


# -- Completion ------------------------------------------------------------

def mark_task_complete(project: Project, task_id: str, completion_date=None):
    """Mark a task complete; if it's a parent, cascade to all descendants.

    Returns a CompletionResult. Pass it to `undo_complete_batch` to revert.
    """
    return _mark_complete(project, task_id, completion_date=completion_date)


def unmark_task_complete(project: Project, task_id: str) -> None:
    """Toggle is_complete: true → false on one task. Does not cascade."""
    _unmark_complete(project, task_id)


def undo_complete_batch(project: Project, result) -> list[str]:
    """Reverse a mark-complete batch. Returns restored task IDs."""
    return _undo_complete(project, result)


# -- Baseline --------------------------------------------------------------

def set_project_baseline(project: Project, overwrite: bool = False):
    """Snapshot current computed dates into each task's baseline_start /
    baseline_finish. Skips tasks that already have a baseline unless
    overwrite=True. Returns a BaselineResult.
    """
    return _set_baseline(project, overwrite=overwrite)


# -- Editing ---------------------------------------------------------------

def add_task(project: Project, **kwargs):
    """Append a task with the next generated TASK-NNN ID."""
    return _add_task(project, **kwargs)


def update_task(project: Project, task_id: str, **kwargs):
    """Update one task's editable fields."""
    return _update_task(project, task_id, **kwargs)


def delete_task(project: Project, task_id: str) -> None:
    """Delete a task if nothing still depends on it and it has no children."""
    _delete_task(project, task_id)


def add_dependency(project: Project, task_id: str, dep_id: str,
                   type: str = "FS", lag_days: int = 0) -> None:
    """Add or update one predecessor dependency on a task."""
    _add_dependency(project, task_id, dep_id, type=type, lag_days=lag_days)


def remove_dependency(project: Project, task_id: str, dep_id: str) -> None:
    """Remove one predecessor dependency from a task."""
    _remove_dependency(project, task_id, dep_id)
