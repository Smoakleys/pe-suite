"""Structured exception hierarchy for the Gantt builder.

All API-surface errors descend from GanttError and carry a serializable envelope
suitable for transmission across the Streamlit boundary or any future HTTP layer.
"""

from __future__ import annotations


class GanttError(Exception):
    """Base class for all Gantt builder errors."""

    error_code: str = "GANTT_ERROR"

    def __init__(self, message: str, affected_tasks: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.affected_tasks = affected_tasks or []

    def to_envelope(self) -> dict:
        return {
            "success": False,
            "error_code": self.error_code,
            "message": self.message,
            "affected_tasks": self.affected_tasks,
        }


class ValidationFailure(GanttError):
    """Raised when logical-tier validation produces one or more errors.

    Carries a list of nested GanttError instances. Use .errors to inspect them.
    """

    error_code = "VALIDATION_FAILURE"

    def __init__(self, errors: list[GanttError]) -> None:
        message = f"Validation failed with {len(errors)} error(s)."
        affected = sorted({t for e in errors for t in e.affected_tasks})
        super().__init__(message, affected_tasks=affected)
        self.errors = errors

    def to_envelope(self) -> dict:
        return {
            "success": False,
            "errors": [e.to_envelope() for e in self.errors],
        }


class StructuralError(GanttError):
    """Tier-1 error: malformed JSON or missing required fields. Fails fast."""

    error_code = "STRUCTURAL_ERROR"


class CircularDependencyError(GanttError):
    error_code = "CIRCULAR_DEPENDENCY"


class MissingDependencyError(GanttError):
    error_code = "MISSING_DEPENDENCY"


class DuplicateTaskIdError(GanttError):
    error_code = "DUPLICATE_TASK_ID"


class SelfDependencyError(GanttError):
    error_code = "SELF_DEPENDENCY"


class InvalidParentRelationshipError(GanttError):
    error_code = "INVALID_PARENT_RELATIONSHIP"


class InvalidCycleTimeError(GanttError):
    error_code = "INVALID_CYCLE_TIME"


class InvalidStartDateError(GanttError):
    error_code = "INVALID_START_DATE"


class InvalidCompletionDateError(GanttError):
    error_code = "INVALID_COMPLETION_DATE"


class UnanchoredTaskError(GanttError):
    error_code = "UNANCHORED_TASK"


class InvalidLocationError(GanttError):
    error_code = "INVALID_LOCATION"


class MissingHolidayDataError(GanttError):
    error_code = "MISSING_HOLIDAY_DATA"


class InvalidDelayDaysError(GanttError):
    error_code = "INVALID_DELAY_DAYS"


class ParentHasCycleTimeError(GanttError):
    error_code = "PARENT_HAS_CYCLE_TIME"


class TaskNotFoundError(GanttError):
    error_code = "TASK_NOT_FOUND"


class CompletedTaskCannotBeDelayedError(GanttError):
    error_code = "COMPLETED_TASK_CANNOT_BE_DELAYED"


class TaskDeletionBlockedError(GanttError):
    error_code = "TASK_DELETION_BLOCKED"
