"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from gantt_builder import api
from gantt_builder.models import Project

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"


@pytest.fixture
def small_demo_path() -> Path:
    return EXAMPLES_DIR / "small_demo.json"


@pytest.fixture
def small_project(small_demo_path: Path) -> Project:
    return api.load_project(small_demo_path)
