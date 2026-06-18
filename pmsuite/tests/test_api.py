"""End-to-end pipeline tests: load -> validate -> schedule -> build Excel."""

from __future__ import annotations

from pathlib import Path

from gantt_builder import api


def test_end_to_end_small_demo(small_project, tmp_path: Path):
    """The walking-skeleton contract: load a project, validate, schedule, build a workbook."""
    warnings = api.validate_project(small_project)
    assert isinstance(warnings, list)

    schedule = api.schedule_project(small_project)
    assert len(schedule) == len(small_project.tasks)

    for task in small_project.tasks:
        assert task.id in schedule
        s = schedule[task.id]
        assert s.computed_start is not None
        assert s.computed_finish is not None
        assert s.computed_finish >= s.computed_start

    output_path = api.build_excel(small_project, output_dir=tmp_path)
    assert output_path.exists()
    assert output_path.suffix == ".xlsx"
    assert output_path.stat().st_size > 0
    assert output_path.name.startswith("gantt_DEMO-SMALL_")


def test_excel_has_required_sheets(small_project, tmp_path: Path):
    """Confirm the mandatory sheets are present in the generated workbook."""
    openpyxl = __import__("openpyxl")
    output_path = api.build_excel(small_project, output_dir=tmp_path)
    wb = openpyxl.load_workbook(str(output_path), read_only=True)
    sheet_names = wb.sheetnames
    assert sheet_names[0] == "Chart Key & Info"
    assert "Chart Key & Info" in sheet_names
    assert "Day View" in sheet_names
    assert "Week View" in sheet_names
    assert "Schedule Calculations" in sheet_names
    assert "Critical Path Notes" in sheet_names
