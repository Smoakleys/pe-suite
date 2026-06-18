"""Structural Excel rendering assertions."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from gantt_builder import api
from gantt_builder.models import HolidayEntry, Project, ProjectMeta, Settings, Task


def _project(tasks: list[Task], next_task_id: int | None = None) -> Project:
    return Project(
        project=ProjectMeta(
            id="EXCEL-TEST",
            name="Excel test",
            timezone="America/Chicago",
            created_at=datetime(2026, 5, 13, 12, 0, 0),
            updated_at=datetime(2026, 5, 13, 12, 0, 0),
        ),
        settings=Settings(
            holidays={"DAL": []},
            work_weeks={"DAL": ["MON", "TUE", "WED", "THU", "FRI"]},
            next_task_id=next_task_id or (len(tasks) + 1),
        ),
        tasks=tasks,
    )


def _task(task_id: str, start: date, name: str | None = None) -> Task:
    return Task(
        id=task_id,
        name=name or task_id,
        completion_location="DAL",
        calendar_mode="e_days",
        cycle_time_days=1,
        manual_start_date=start,
    )


def test_working_day_holiday_gap_uses_holiday_fill(tmp_path: Path):
    project = _project(
        [
            Task(
                id="TASK-001",
                name="Working task over holiday",
                completion_location="DAL",
                calendar_mode="working_days",
                cycle_time_days=3,
                manual_start_date=date(2026, 5, 18),
            ),
        ],
        next_task_id=2,
    )
    project.settings.holidays["DAL"] = [
        HolidayEntry(date=date(2026, 5, 19), name="Test Holiday", source="user-added"),
    ]

    output = api.build_excel(project, output_dir=tmp_path)

    openpyxl = __import__("openpyxl")
    wb = openpyxl.load_workbook(str(output))
    sheet = wb["Day View"]

    holiday_col = None
    for cell in sheet[1]:
        if isinstance(cell.value, str) and "2026-05-19" in cell.value:
            holiday_col = cell.column
            break

    assert holiday_col is not None
    holiday_cell = sheet.cell(row=2, column=holiday_col)
    assert holiday_cell.fill.fgColor.rgb == "FFB0B0B0"


def test_gantt_views_sort_rows_chronologically_without_renumbering(tmp_path: Path):
    project = _project(
        [
            _task("TASK-009", date(2026, 5, 18)),
            _task("TASK-010", date(2026, 5, 25)),
            _task("TASK-013", date(2026, 5, 20)),
        ],
        next_task_id=14,
    )

    output = api.build_excel(project, output_dir=tmp_path)

    openpyxl = __import__("openpyxl")
    wb = openpyxl.load_workbook(str(output), read_only=True)

    for sheet_name in ("Day View", "Week View"):
        sheet = wb[sheet_name]
        task_ids = [sheet.cell(row=row, column=1).value for row in range(2, 5)]
        assert task_ids == ["TASK-009", "TASK-013", "TASK-010"]


def test_chart_key_documents_row_order_and_has_wide_wrapped_columns(tmp_path: Path):
    project = _project([_task("TASK-001", date(2026, 5, 18))])

    output = api.build_excel(project, output_dir=tmp_path)

    openpyxl = __import__("openpyxl")
    wb = openpyxl.load_workbook(str(output))
    sheet = wb["Chart Key & Info"]
    values = [cell.value for row in sheet.iter_rows() for cell in row if isinstance(cell.value, str)]

    assert "Task Row Order" in values
    assert any("TASK-013" in value and "TASK-009" in value for value in values)
    assert sheet.column_dimensions["A"].width >= 26
    assert sheet.column_dimensions["B"].width >= 36
    assert sheet.column_dimensions["C"].width >= 118


def test_day_and_week_views_keep_compact_timeline_columns(tmp_path: Path):
    project = _project([_task("TASK-001", date(2026, 5, 18))])

    output = api.build_excel(project, output_dir=tmp_path)

    openpyxl = __import__("openpyxl")
    wb = openpyxl.load_workbook(str(output))
    try:
        day = wb["Day View"]
        week = wb["Week View"]

        assert 28 <= day.column_dimensions["B"].width < 29
        assert 4 <= day.column_dimensions["H"].width < 5
        assert 28 <= week.column_dimensions["B"].width < 29
        assert 12 <= week.column_dimensions["H"].width < 13
    finally:
        wb.close()
