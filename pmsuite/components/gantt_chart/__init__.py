"""PMSuite Interactive Gantt Chart - Streamlit custom component."""

from pathlib import Path

import streamlit.components.v1 as components

_RELEASE = True
_COMPONENT_NAME = "pmsuite_gantt"

if _RELEASE:
    _build_dir = Path(__file__).parent / "frontend" / "build"
    _component_func = components.declare_component(_COMPONENT_NAME, path=str(_build_dir))
else:
    _component_func = components.declare_component(
        _COMPONENT_NAME, url="http://localhost:3000"
    )


def st_gantt(
    tasks: list[dict],
    dependencies: list[dict],
    view_mode: str = "Week",
    selected_task_id: str | None = None,
    today_scroll: bool = False,
    search_query: str = "",
    sidebar_visible: bool = True,
    key: str | None = None,
) -> dict | None:
    """Render the interactive Gantt chart component.

    Args:
        tasks: List of task dicts with id, name, start, end, progress,
               custom_class, parent_id, hierarchy_level, etc.
        dependencies: List of dependency dicts with from_id, to_id, type.
        view_mode: "Day", "Week", or "Month".
        selected_task_id: Currently selected task ID (for highlighting).
        today_scroll: If True, scroll to today on next render.
        search_query: Current search filter text.
        sidebar_visible: Whether the sidebar is shown (affects chart width).
        key: Streamlit component key for session state.

    Returns:
        Event dict from JS (click, drag, dependency create/delete, etc.)
        or None if no event fired.
    """
    event = _component_func(
        tasks=tasks,
        dependencies=dependencies,
        view_mode=view_mode,
        selected_task_id=selected_task_id,
        today_scroll=today_scroll,
        search_query=search_query,
        sidebar_visible=sidebar_visible,
        key=key,
        default=None,
    )
    return event
