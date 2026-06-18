"""Load and save project JSON files.

Save uses atomic write (temp file + os.replace) so a partial file is never left
on disk if the process dies mid-write. Optional rotating snapshots are written
to projects/.backups/<project_id>/ on each save (FIFO, capped by
settings.keep_local_snapshots).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .errors import StructuralError
from .logging_config import get_logger
from .models import Project
from .time_utils import project_now

_log = get_logger(__name__)


def load_project(path: str | Path) -> Project:
    """Load a project from a JSON file. Raises StructuralError on parse failure."""
    path = Path(path)
    if not path.exists():
        raise StructuralError(f"Project file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise StructuralError(f"Malformed JSON in {path}: {exc}") from exc

    try:
        project = Project.model_validate(data)
    except Exception as exc:
        raise StructuralError(f"Project schema invalid: {exc}") from exc

    _log.info("Loaded project %s from %s (%d tasks)", project.project.id, path, len(project.tasks))
    return project


def save_project(project: Project, path: str | Path) -> None:
    """Atomically write the project JSON to `path`.

    Process:
    1. Update project.updated_at.
    2. Serialize to a temp file in the same directory.
    3. os.replace the temp file over the destination.
    4. Optionally retain a rotating snapshot in projects/.backups/<project_id>/.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    now = project_now(project)
    project.project.updated_at = now

    payload = project.model_dump(mode="json", exclude_defaults=False, exclude_none=False)
    json_text = json.dumps(payload, indent=2, ensure_ascii=False)

    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=f"{path.stem}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(json_text)
        os.replace(tmp_path, path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise

    _log.info("Saved project %s to %s", project.project.id, path)

    if project.settings.keep_local_snapshots > 0:
        _write_snapshot(project, path, json_text, now)


def _write_snapshot(project: Project, project_path: Path, json_text: str, now) -> None:
    """Write a rotating snapshot under projects/.backups/<project_id>/."""
    snapshot_dir = project_path.parent / ".backups" / project.project.id
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    timestamp = now.strftime("%Y-%m-%d_%H%M%S")
    snapshot_file = snapshot_dir / f"{project.project.id}_{timestamp}.json"
    snapshot_file.write_text(json_text, encoding="utf-8")

    # Prune oldest snapshots
    existing = sorted(snapshot_dir.glob(f"{project.project.id}_*.json"))
    to_remove = existing[: -project.settings.keep_local_snapshots] if len(existing) > project.settings.keep_local_snapshots else []
    for old in to_remove:
        old.unlink(missing_ok=True)
