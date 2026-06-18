"""Tests for the pydantic data models."""

from __future__ import annotations

from datetime import date

from gantt_builder.models import Dependency, Task


def test_dependency_full_object_form():
    dep = Dependency(id="TASK-001", type="SS", lag_days=2)
    assert dep.id == "TASK-001"
    assert dep.type == "SS"
    assert dep.lag_days == 2


def test_dependency_defaults_to_fs_zero_lag():
    dep = Dependency(id="TASK-001")
    assert dep.type == "FS"
    assert dep.lag_days == 0


def test_task_dependency_string_shorthand_is_normalized():
    t = Task(
        id="TASK-002",
        name="Test",
        completion_location="DAL",
        calendar_mode="e_days",
        cycle_time_days=1,
        manual_start_date=date(2026, 5, 18),
        dependencies=["TASK-001"],
    )
    assert len(t.dependencies) == 1
    assert t.dependencies[0].id == "TASK-001"
    assert t.dependencies[0].type == "FS"
    assert t.dependencies[0].lag_days == 0


def test_task_dependency_mixed_forms_are_normalized():
    t = Task(
        id="TASK-003",
        name="Test",
        completion_location="DAL",
        calendar_mode="e_days",
        cycle_time_days=1,
        manual_start_date=date(2026, 5, 18),
        dependencies=[
            "TASK-001",
            {"id": "TASK-002", "type": "SS", "lag_days": 3},
        ],
    )
    assert t.dependencies[0].type == "FS"
    assert t.dependencies[1].type == "SS"
    assert t.dependencies[1].lag_days == 3
