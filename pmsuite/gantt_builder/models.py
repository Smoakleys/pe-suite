"""Pydantic v2 models for the Project / Task / Dependency data graph.

The JSON project file is the source of truth. These models serialize to/from JSON
canonically (all fields explicit with defaults, predictable diff in git).

Derived fields (has_subtasks, computed_start, effective_finish, etc.) are NOT
stored — they are computed properties resolved at runtime.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Dependency(BaseModel):
    """A dependency edge from this task to a predecessor.

    Bare string form (e.g., "TASK-001") is accepted by the parent Task model's
    validator as shorthand for FS, 0-lag.
    """

    id: str
    type: Literal["FS", "SS", "FF", "SF"] = "FS"
    lag_days: int = 0

    model_config = ConfigDict(extra="forbid")


class DelayLogEntry(BaseModel):
    """Audit entry for a single delay application."""

    date: date
    source: Literal["manual", "auto"]
    days_added: int
    reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class HolidayEntry(BaseModel):
    """A holiday observance for a location."""

    date: date
    name: str
    source: Literal["seeded", "user-added", "user-edited"] = "user-added"

    model_config = ConfigDict(extra="forbid")


class Task(BaseModel):
    """A single task (leaf or parent) in the project.

    Parents are identified by having other tasks with parent_id == this.id.
    Parents must NOT carry cycle_time_days (validation enforces).

    `baseline_start` and `baseline_finish` are the user-committed planned
    dates captured by `set_project_baseline()`. They never change with
    delays or completion — they represent the original plan for variance
    reporting in the Gantt views. None means baseline has not yet been set.
    """

    id: str
    name: str
    completion_location: str
    calendar_mode: Literal["working_days", "e_days"]
    cycle_time_days: int | None = None
    manual_start_date: date | None = None
    baseline_start: date | None = None
    baseline_finish: date | None = None
    dependencies: list[Dependency] = Field(default_factory=list)
    parent_id: str | None = None
    is_complete: bool = False
    actual_completion_date: date | None = None
    delay_days: int = 0
    delay_log: list[DelayLogEntry] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("dependencies", mode="before")
    @classmethod
    def _normalize_dependencies(cls, v):
        """Accept bare strings as shorthand for FS dependencies with 0 lag."""
        if v is None:
            return []
        normalized = []
        for item in v:
            if isinstance(item, str):
                normalized.append({"id": item, "type": "FS", "lag_days": 0})
            else:
                normalized.append(item)
        return normalized


class LastExport(BaseModel):
    """Metadata about the most recent Excel export."""

    path: str
    at: datetime

    model_config = ConfigDict(extra="forbid")


class HistoryEntry(BaseModel):
    """Snapshot captured at the moment a task is marked complete.

    Stores derived facts (e.g., whether the task was on the critical path)
    that would otherwise be lost when scheduling state changes.
    """

    task_id: str
    was_on_critical_path: bool
    captured_at: datetime

    model_config = ConfigDict(extra="forbid")


class ProjectMeta(BaseModel):
    """Top-level project metadata."""

    id: str
    name: str
    timezone: str = "America/Chicago"
    created_at: datetime
    updated_at: datetime
    last_export: LastExport | None = None
    history: list[HistoryEntry] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class Settings(BaseModel):
    """Project-wide settings."""

    holidays: dict[str, list[HolidayEntry]] = Field(default_factory=dict)
    work_weeks: dict[str, list[str]] = Field(default_factory=dict)
    next_task_id: int = 1
    output_directory: str = "output"
    keep_local_snapshots: int = 10
    auto_delay_on_load: bool = True
    last_auto_delay_run: date | None = None
    date_axis_start: date | None = None
    date_axis_end: date | None = None

    model_config = ConfigDict(extra="forbid")


class Project(BaseModel):
    """The full project: metadata + settings + tasks. The JSON source of truth."""

    project: ProjectMeta
    settings: Settings
    tasks: list[Task] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    # Computed convenience accessors (NOT stored in JSON)
    def task_by_id(self, task_id: str) -> Task | None:
        return next((t for t in self.tasks if t.id == task_id), None)

    def children_of(self, task_id: str) -> list[Task]:
        return [t for t in self.tasks if t.parent_id == task_id]

    def has_subtasks(self, task_id: str) -> bool:
        return any(t.parent_id == task_id for t in self.tasks)

    def is_leaf(self, task_id: str) -> bool:
        return not self.has_subtasks(task_id)

    def all_descendant_ids(self, task_id: str) -> list[str]:
        """All descendant task IDs (leaves and intermediate parents) under task_id."""
        result: list[str] = []
        visited: set[str] = {task_id}
        stack: list[str] = [task_id]
        while stack:
            current = stack.pop()
            for child in self.children_of(current):
                if child.id in visited:
                    continue
                visited.add(child.id)
                result.append(child.id)
                stack.append(child.id)
        return result

    def all_descendant_leaf_ids(self, task_id: str) -> list[str]:
        """Only the LEAF descendants under task_id."""
        return [d for d in self.all_descendant_ids(task_id) if not self.has_subtasks(d)]
