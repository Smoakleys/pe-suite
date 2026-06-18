"""Canonical on-disk locations for the fetch side (no deps, importable anywhere).

The fetch service owns its storage, so these live here; `pesuite.config` re-exports
them. The store and the browser profile are hidden under the per-user app-data dir and
are never placed in the projects folder or shown to users.
"""

from __future__ import annotations

import os
from pathlib import Path


def app_data_dir() -> Path:
    """Windows: %LOCALAPPDATA%\\PESuite. Falls back to ~/.local/share/PESuite."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    d = Path(base) / "PESuite"
    d.mkdir(parents=True, exist_ok=True)
    return d


def fetch_store_path() -> Path:
    return app_data_dir() / "fetch_store.sqlite3"


def browser_profile_dir() -> Path:
    d = app_data_dir() / "browser_profile"
    d.mkdir(parents=True, exist_ok=True)
    return d
