"""Tests for JSON load/save round-tripping and atomic writes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gantt_builder import api
from gantt_builder.errors import StructuralError


def test_load_small_demo(small_project):
    assert small_project.project.id == "DEMO-SMALL"
    assert len(small_project.tasks) > 0


def test_load_missing_file_raises(tmp_path: Path):
    with pytest.raises(StructuralError):
        api.load_project(tmp_path / "does_not_exist.json")


def test_load_malformed_json_raises(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(StructuralError):
        api.load_project(bad)


def test_save_and_reload_round_trip(small_project, tmp_path: Path):
    out_path = tmp_path / "roundtrip.json"
    small_project.settings.keep_local_snapshots = 0  # no snapshots in tmp
    api.save_project(small_project, out_path)
    assert out_path.exists()

    reloaded = api.load_project(out_path)
    assert reloaded.project.id == small_project.project.id
    assert len(reloaded.tasks) == len(small_project.tasks)
    assert reloaded.tasks[0].id == small_project.tasks[0].id


def test_save_writes_canonical_with_defaults(small_project, tmp_path: Path):
    out_path = tmp_path / "canonical.json"
    small_project.settings.keep_local_snapshots = 0
    api.save_project(small_project, out_path)

    data = json.loads(out_path.read_text(encoding="utf-8"))
    # Every task should serialize with all fields explicit
    for task in data["tasks"]:
        for field in ("id", "name", "completion_location", "calendar_mode",
                      "dependencies", "is_complete", "delay_days"):
            assert field in task


def test_save_uses_project_timezone_for_updated_at(small_project, tmp_path: Path):
    out_path = tmp_path / "timezone.json"
    small_project.project.timezone = "Asia/Tokyo"
    small_project.settings.keep_local_snapshots = 0

    api.save_project(small_project, out_path)

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["project"]["updated_at"].endswith("+09:00")


def test_build_excel_sets_last_export_in_project_timezone(small_project, tmp_path: Path):
    small_project.project.timezone = "Asia/Tokyo"

    api.build_excel(small_project, output_dir=tmp_path)

    assert small_project.project.last_export is not None
    assert small_project.project.last_export.at.utcoffset().total_seconds() == 9 * 60 * 60
