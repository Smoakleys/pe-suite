"""Baseline snapshot: capture the current planned dates as the reference plan.

A 'baseline' is the user-committed planned dates at a moment in time —
typically just before project execution begins. After baselining, the
Gantt views can show variance between baseline (the original promise)
and the current schedule (which may have shifted due to delays or
completion).

set_project_baseline() runs the scheduler and copies each task's
computed_start / computed_finish into baseline_start / baseline_finish.
Tasks already complete keep their existing baseline if any (we don't
overwrite history). Re-baselining is allowed via overwrite=True.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .logging_config import get_logger
from .models import Project
from .scheduler import run_schedule

_log = get_logger(__name__)


@dataclass
class BaselineResult:
    """Outcome of a set_project_baseline call."""

    tasks_baselined: list[str] = field(default_factory=list)
    tasks_skipped: list[str] = field(default_factory=list)

    @property
    def count_baselined(self) -> int:
        return len(self.tasks_baselined)


def set_project_baseline(project: Project, overwrite: bool = False) -> BaselineResult:
    """Snapshot each task's computed_start / computed_finish into baseline_*.

    By default, tasks that already have a baseline (baseline_start is not None)
    are left untouched. Pass overwrite=True to re-baseline every task.

    Mutates the project in place. Returns a BaselineResult listing the task
    IDs that were updated and those that were skipped.
    """
    schedule = run_schedule(project)
    result = BaselineResult()

    for task in project.tasks:
        s = schedule.get(task.id)
        if s is None:
            result.tasks_skipped.append(task.id)
            continue

        if task.baseline_start is not None and not overwrite:
            result.tasks_skipped.append(task.id)
            continue

        task.baseline_start = s.computed_start
        task.baseline_finish = s.computed_finish
        result.tasks_baselined.append(task.id)

    _log.info(
        "Baseline set on project %s: %d baselined, %d skipped (overwrite=%s)",
        project.project.id, len(result.tasks_baselined), len(result.tasks_skipped), overwrite,
    )

    return result
