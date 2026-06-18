"""Runtime configuration: where things live on disk.

Kept tiny and dependency-free so any layer can import it. The projects directory is
the shared source-of-truth folder — the SAME folder the Streamlit editor reads and
writes (`pmsuite/projects/`), so PE Suite and the editor never diverge.
"""

from __future__ import annotations

import os
from pathlib import Path

# pe-suite/ repo root (this file is pe-suite/pesuite/config.py).
REPO_ROOT = Path(__file__).resolve().parent.parent
PMSUITE_DIR = REPO_ROOT / "pmsuite"


def projects_dir() -> Path:
    """The shared projects/ folder, owned by the PMSuite engine/editor.

    Override with PESUITE_PROJECTS_DIR (must also match the editor's projects dir).
    """
    env = os.environ.get("PESUITE_PROJECTS_DIR")
    return Path(env).expanduser() if env else PMSUITE_DIR / "projects"


def streamlit_script() -> Path:
    """The Streamlit editor entry point, launched by the Gantt pane's Launch Editor."""
    return PMSUITE_DIR / "ui" / "streamlit_app.py"


# Hidden fetch-side storage locations are owned by fetch_service; re-export them so the
# UI has one import surface (`pesuite.config`) without reaching past the boundary.
from fetch_service.paths import (  # noqa: E402
    app_data_dir,
    browser_profile_dir,
    fetch_store_path,
)

__all__ = [
    "REPO_ROOT", "PMSUITE_DIR", "projects_dir", "streamlit_script",
    "app_data_dir", "browser_profile_dir", "fetch_store_path",
]
