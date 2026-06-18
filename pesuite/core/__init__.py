"""Core read layer: project discovery, loading, and derived views.

This package is the boundary between PMSuite's `gantt_builder` engine and the rest
of PE Suite. The UI imports from here and never touches pydantic models or engine
internals directly — it consumes the plain dataclasses produced in `views`.

Rule: this layer is *read-only and pure*. It loads project JSON and derives views.
It never fetches external data and never imports the UI.
"""

from .projects import ProjectRef, LoadedProject, discover_projects, load_project
from .views import (
    TaskRow,
    PriorityItem,
    TaskStatus,
    task_rows,
    priorities,
)

__all__ = [
    "ProjectRef",
    "LoadedProject",
    "discover_projects",
    "load_project",
    "TaskRow",
    "PriorityItem",
    "TaskStatus",
    "task_rows",
    "priorities",
]
