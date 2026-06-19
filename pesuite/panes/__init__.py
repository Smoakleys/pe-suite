"""The panes. Each consumes `pesuite.core` dataclasses and/or the FetchClient."""

from .gantt_pane import GanttPane
from .tasks_pane import TasksPane
from .priorities_pane import PrioritiesPane
from .updates_pane import UpdatesPane
from .material_pane import MaterialPane

__all__ = ["GanttPane", "TasksPane", "PrioritiesPane", "UpdatesPane", "MaterialPane"]
