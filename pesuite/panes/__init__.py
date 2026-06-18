"""The five panes. Each consumes `pesuite.core` dataclasses and `AppState` signals."""

from .gantt_pane import GanttPane
from .tasks_pane import TasksPane
from .priorities_pane import PrioritiesPane
from .updates_pane import UpdatesPane

__all__ = ["GanttPane", "TasksPane", "PrioritiesPane", "UpdatesPane"]
