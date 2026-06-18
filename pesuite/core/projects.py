"""Project discovery and loading.

`discover_projects` enumerates the shared `projects/` folder (the same folder the
Streamlit editor reads and writes) and returns lightweight refs for the global
selector. `load_project` reads one project and bundles it with its computed schedule
and critical path, so every derived view works from a single consistent snapshot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from gantt_builder import api
from gantt_builder.critical_path import CriticalPathResult, compute_critical_path
from gantt_builder.models import Project
from gantt_builder.scheduler import ScheduledTask
from gantt_builder.time_utils import project_now


@dataclass(frozen=True)
class ProjectRef:
    """A lightweight pointer to a project file, for the global selector.

    Cheap to build (reads only id + name), so the selector can list many projects
    without scheduling any of them.
    """

    id: str
    name: str
    path: Path


@dataclass(frozen=True)
class LoadedProject:
    """A project plus its computed schedule and critical path.

    One immutable snapshot. Every derived view (Tasks, Priorities, Gantt geometry)
    reads from this, so they can never disagree about dates.
    """

    ref: ProjectRef
    project: Project
    schedule: dict[str, ScheduledTask]
    critical: CriticalPathResult
    today: date

    @property
    def project_end(self) -> date | None:
        return self.critical.project_end


def discover_projects(projects_dir: str | Path) -> list[ProjectRef]:
    """Return a ref for every `*.json` project in `projects_dir`, sorted by name.

    Unreadable or malformed files are skipped rather than raising, so one bad file
    never breaks the selector. Reads only the metadata block, not the full project.
    """
    root = Path(projects_dir)
    refs: list[ProjectRef] = []
    if not root.is_dir():
        return refs

    for path in sorted(root.glob("*.json")):
        ref = _read_ref(path)
        if ref is not None:
            refs.append(ref)

    refs.sort(key=lambda r: r.name.lower())
    return refs


def _read_ref(path: Path) -> ProjectRef | None:
    """Best-effort read of a project's id + name without full validation."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        meta = data.get("project", {})
        pid = meta.get("id") or path.stem
        name = meta.get("name") or path.stem
        return ProjectRef(id=str(pid), name=str(name), path=path)
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def load_project(path: str | Path, today: date | None = None) -> LoadedProject:
    """Load one project and compute its schedule + critical path.

    `today` defaults to the project's local "now" (its configured timezone), which is
    what overdue/due-soon status is measured against. Inject a fixed date for testing.
    """
    path = Path(path)
    project = api.load_project(path)
    schedule = api.schedule_project(project)
    critical = compute_critical_path(project, schedule)

    if today is None:
        today = project_now(project).date()

    ref = ProjectRef(id=project.project.id, name=project.project.name, path=path)
    return LoadedProject(
        ref=ref,
        project=project,
        schedule=schedule,
        critical=critical,
        today=today,
    )
