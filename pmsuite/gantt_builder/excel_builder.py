"""Excel workbook generation via xlsxwriter (full Option E rendering).

Produces a 5-sheet workbook:
  - Chart Key & Info         — legend and workbook-reading guide
  - Day View                 — segmented colored cell bars, per-day resolution
  - Week View                — same span, weekly aggregation
  - Schedule Calculations    — auditable per-task table
  - Critical Path Notes      — risk/timing dashboard

Bar segments per Option E:
  - Planned (incomplete)    : pale blue
  - Completed (full bar)    : green
  - Delay extension         : orange (computed_finish < d <= effective_finish)
  - Overdue tail            : red    (today > effective_finish, incomplete)
  - Critical path           : dark red top/bottom border on the bar
  - Today column            : thick black left border + yellow header
  - Weekend / holiday gap   : light gray (only for working_day tasks on their
                              own non-working days INSIDE the bar range)
  - Parent summary          : dark gray with cap borders

Gantt row ordering:
  - Day View and Week View sort rows chronologically by computed schedule dates.
    Task IDs remain stable identifiers and do not imply display order.

Column header styling:
  - Today column      : yellow fill
  - Weekend           : light gray
  - Holiday (any loc) : darker gray + holiday name appended

Frozen-pane metadata columns: TASK ID, Name, Location, Cycle Time (Days),
Baseline Start, Baseline Finish, Dependencies.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import xlsxwriter

from .critical_path import CriticalPathResult
from .locations import weekday_code
from .logging_config import get_logger
from .models import Project
from .scheduler import ScheduledTask
from .time_utils import project_now

_log = get_logger(__name__)


# Frozen-pane metadata columns (left of the date axis)
_METADATA_COLS = [
    "TASK ID", "Name", "Location", "Cycle Time (Days)",
    "Baseline Start", "Baseline Finish", "Dependencies",
]
_METADATA_COL_COUNT = len(_METADATA_COLS)


def _short_dep_ids(task) -> str:
    """Format dependencies as comma-separated numerical task IDs.

    e.g., a task depending on TASK-002 and TASK-007 renders as "002, 007".
    Empty string for tasks with no dependencies.
    """
    if not task.dependencies:
        return ""
    return ", ".join(d.id.split("-")[-1] for d in task.dependencies)


# -------------------------------------------------------------------------
# Public entry point

def build_excel(
    project: Project,
    schedule: dict[str, ScheduledTask],
    critical_path: CriticalPathResult,
    output_dir: str | Path | None = None,
) -> Path:
    """Generate the Excel workbook and return the output path."""
    output_dir = Path(output_dir) if output_dir else Path(project.settings.output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = project_now(project).strftime("%Y-%m-%d_%H%M%S")
    filename = f"gantt_{project.project.id}_{timestamp}.xlsx"
    path = output_dir / filename

    counter = 2
    while path.exists():
        filename = f"gantt_{project.project.id}_{timestamp}_{counter}.xlsx"
        path = output_dir / filename
        counter += 1

    workbook = xlsxwriter.Workbook(str(path))
    formats = _build_formats(workbook)
    axis_start, axis_end = _compute_axis(project, schedule)

    _build_chart_key_info(workbook, project, formats)
    _build_day_view(workbook, project, schedule, critical_path, formats, axis_start, axis_end)
    _build_week_view(workbook, project, schedule, critical_path, formats, axis_start, axis_end)
    _build_schedule_calculations(workbook, project, schedule, critical_path, formats)
    _build_critical_path_notes(workbook, project, schedule, critical_path, formats)

    workbook.close()
    _log.info("Built Excel workbook %s for project %s", path, project.project.id)
    return path


# -------------------------------------------------------------------------
# Format precomputation

# Color palette (DESIGN.md §14.4 / Q26a, with iteration after checkpoint 2)
_C_PLANNED   = "#8FB6E1"   # pale blue for critical-border contrast
_C_COMPLETED = "#2E8B57"
_C_DELAYED   = "#E68A00"
_C_OVERDUE   = "#D9534F"
_C_WEEKEND   = "#F0F0F0"
_C_HOLIDAY   = "#B0B0B0"   # visible holiday gray in Excel viewers
_C_TODAY     = "#FFF8C4"
_C_PARENT    = "#555555"
_C_CRITICAL_BORDER = "#8B0000"
_C_HEADER    = "#D9D9D9"


def _build_formats(workbook) -> dict:
    formats: dict = {}

    # -- Header variants -----------------------------------------------
    base_header = {
        "bold": True, "border": 1, "align": "center", "valign": "vcenter",
        "text_wrap": True, "font_size": 9,
    }
    formats["header"]         = workbook.add_format({**base_header, "bg_color": _C_HEADER})
    formats["header_today"]   = workbook.add_format({**base_header, "bg_color": _C_TODAY})
    formats["header_weekend"] = workbook.add_format({**base_header, "bg_color": _C_WEEKEND})
    formats["header_holiday"] = workbook.add_format({**base_header, "bg_color": _C_HOLIDAY})

    # -- Task metadata cells -------------------------------------------
    formats["task_id"] = workbook.add_format({
        "font_name": "Consolas", "border": 1, "text_wrap": True, "valign": "top",
    })
    formats["task_name"] = workbook.add_format({
        "border": 1, "text_wrap": True, "valign": "top",
    })

    # -- Body cell formats (one per status × critical × today combination) -
    body_status_fills = {
        "planned":   _C_PLANNED,
        "completed": _C_COMPLETED,
        "delayed":   _C_DELAYED,
        "overdue":   _C_OVERDUE,
        "parent":    _C_PARENT,
    }
    for status, fill in body_status_fills.items():
        for is_critical in (False, True):
            for is_today in (False, True):
                key = status
                if is_critical:
                    key += "_critical"
                if is_today:
                    key += "_today"
                spec = {"bg_color": fill, "border": 1}
                if is_critical and status != "overdue":
                    # Critical: thicker dark-red top + bottom border
                    spec.update({"top": 2, "bottom": 2,
                                 "top_color": _C_CRITICAL_BORDER,
                                 "bottom_color": _C_CRITICAL_BORDER})
                if is_today:
                    spec.update({"left": 5, "left_color": "#000000"})
                formats[key] = workbook.add_format(spec)

    # -- Non-working-day "gap" cells inside a working-day task's bar ---
    for is_today in (False, True):
        spec = {"bg_color": _C_WEEKEND, "border": 1, "border_color": "#CCCCCC"}
        if is_today:
            spec.update({"left": 5, "left_color": "#000000"})
        formats["weekend_gap_today" if is_today else "weekend_gap"] = workbook.add_format(spec)

        spec_h = {"bg_color": _C_HOLIDAY, "border": 1, "border_color": "#CCCCCC"}
        if is_today:
            spec_h.update({"left": 5, "left_color": "#000000"})
        formats["holiday_gap_today" if is_today else "holiday_gap"] = workbook.add_format(spec_h)

    # -- Empty cell in today's column (yellow tint to indicate today line) -
    formats["empty_today"] = workbook.add_format({
        "bg_color": _C_TODAY, "left": 5, "left_color": "#000000",
    })

    # -- Critical Path Notes / Schedule Calculations helpers -----------
    formats["summary_label"] = workbook.add_format({"bold": True, "text_wrap": True, "valign": "top"})
    formats["summary_value"] = workbook.add_format({"text_wrap": True, "valign": "top"})
    formats["calc_cell"] = workbook.add_format({"text_wrap": True, "valign": "top"})

    return formats


# -------------------------------------------------------------------------
# Axis computation

def _compute_axis(project: Project, schedule: dict[str, ScheduledTask]) -> tuple[date, date]:
    """Padded + Monday-aligned axis per DESIGN.md Q19."""
    today = date.today()

    if schedule:
        earliest_start = min(s.computed_start for s in schedule.values())
        latest_finish = max(s.effective_finish for s in schedule.values())
    else:
        earliest_start = today
        latest_finish = today

    if project.settings.date_axis_start is not None:
        start_axis = project.settings.date_axis_start
    else:
        raw_start = min(earliest_start, today) - timedelta(days=7)
        start_axis = raw_start - timedelta(days=raw_start.weekday())  # back to Monday

    if project.settings.date_axis_end is not None:
        end_axis = project.settings.date_axis_end
    else:
        raw_end = max(latest_finish, today) + timedelta(days=14)
        end_axis = raw_end + timedelta(days=(6 - raw_end.weekday()))  # forward to Sunday

    return start_axis, end_axis


# -------------------------------------------------------------------------
# Shared row writing helpers

def _write_task_metadata_row(sheet, row_idx: int, task, formats, indent: int = 0) -> None:
    """Write the seven frozen-pane metadata columns for one task row."""
    sheet.write(row_idx, 0, task.id, formats["task_id"])
    name_display = ("  " * indent + task.name) if indent > 0 else task.name
    sheet.write(row_idx, 1, name_display, formats["task_name"])
    sheet.write(row_idx, 2, task.completion_location, formats["task_name"])
    sheet.write(row_idx, 3,
                task.cycle_time_days if task.cycle_time_days is not None else "",
                formats["task_name"])
    sheet.write(row_idx, 4,
                task.baseline_start.isoformat() if task.baseline_start else "",
                formats["task_name"])
    sheet.write(row_idx, 5,
                task.baseline_finish.isoformat() if task.baseline_finish else "",
                formats["task_name"])
    sheet.write(row_idx, 6, _short_dep_ids(task), formats["task_name"])


def _set_metadata_column_widths(sheet) -> None:
    """Width spec for the frozen metadata block."""
    sheet.set_column(0, 0, 12)   # TASK ID
    sheet.set_column(1, 1, 28)   # Name
    sheet.set_column(2, 2, 10)   # Location
    sheet.set_column(3, 3, 8)    # Cycle Time (Days)
    sheet.set_column(4, 5, 13)   # Baseline Start / Baseline Finish
    sheet.set_column(6, 6, 14)   # Dependencies (numerical IDs)


def _gantt_task_order(project: Project, schedule: dict[str, ScheduledTask]) -> list:
    """Tasks in hierarchy-aware Gantt row order.

    Parent tasks appear above their children (pre-order tree walk). Siblings
    at the same level sort chronologically by scheduled dates. This ordering
    enables Excel row grouping: children collapse under their parent row.
    """

    def _sort_key(task):
        s = schedule.get(task.id)
        if s is None:
            return (date.max, date.max, task.id)
        return (s.computed_start, s.effective_finish, task.id)

    def _walk(parent_id: str | None) -> list:
        children = [t for t in project.tasks if t.parent_id == parent_id]
        children.sort(key=_sort_key)
        result = []
        for child in children:
            result.append(child)
            result.extend(_walk(child.id))
        return result

    return _walk(None)


def _build_holiday_name_map(project: Project) -> dict[date, str]:
    """For each holiday date, build a summary string spanning all locations.

    Format: "Independence Day (DAL); Eid (MLA, TIEMA)"
    """
    by_date: dict[date, dict[str, list[str]]] = {}
    for loc, entries in project.settings.holidays.items():
        for h in entries:
            by_date.setdefault(h.date, {}).setdefault(h.name, []).append(loc)

    result: dict[date, str] = {}
    for d, name_to_locs in by_date.items():
        parts = [f"{name} ({', '.join(sorted(locs))})" for name, locs in name_to_locs.items()]
        result[d] = "; ".join(parts)
    return result


# -------------------------------------------------------------------------
# Day View — full Option E rendering

def _build_day_view(workbook, project: Project, schedule, critical_path, formats,
                    axis_start: date, axis_end: date) -> None:
    sheet = workbook.add_worksheet("Day View")
    today = date.today()
    critical_set = critical_path.critical_task_ids
    holiday_names = _build_holiday_name_map(project)

    # -- Metadata column headers --
    for c, h in enumerate(_METADATA_COLS):
        sheet.write(0, c, h, formats["header"])

    # -- Date column headers (with weekday, date, holiday names) --
    date_columns: list[tuple[int, date]] = []
    current = axis_start
    col = _METADATA_COL_COUNT
    while current <= axis_end:
        weekday = current.strftime("%a")
        text = f"{weekday}\n{current.isoformat()}"
        if current in holiday_names:
            text += f"\n{holiday_names[current]}"

        is_today_col = (current == today)
        is_holiday   = current in holiday_names
        is_weekend   = weekday in ("Sat", "Sun")

        if is_today_col:
            fmt = formats["header_today"]
        elif is_holiday:
            fmt = formats["header_holiday"]
        elif is_weekend:
            fmt = formats["header_weekend"]
        else:
            fmt = formats["header"]

        sheet.write(0, col, text, fmt)
        date_columns.append((col, current))
        current += timedelta(days=1)
        col += 1

    sheet.set_row(0, 90)  # tall header for multi-line date + holiday text
    _set_metadata_column_widths(sheet)
    sheet.set_column(_METADATA_COL_COUNT, col - 1, 4)
    sheet.freeze_panes(1, _METADATA_COL_COUNT)
    sheet.outline_settings(True, False, False, False)

    # -- Task rows --
    for row_idx, task in enumerate(_gantt_task_order(project, schedule), start=1):
        level = _hierarchy_level(project, task.id)
        sheet.set_row(row_idx, 30, None, {"level": level} if level > 0 else None)
        _write_task_metadata_row(sheet, row_idx, task, formats, indent=level)
        s = schedule.get(task.id)
        if not s:
            continue

        is_critical = task.id in critical_set

        if project.has_subtasks(task.id):
            _render_parent_bar_day(sheet, row_idx, date_columns, s, formats, is_critical, today)
        else:
            _render_leaf_bar_day(sheet, row_idx, date_columns, s, task, project,
                                 formats, is_critical, today)


def _render_leaf_bar_day(sheet, row_idx, date_columns, s, task, project,
                          formats, is_critical: bool, today: date) -> None:
    work_week = set(project.settings.work_weeks.get(task.completion_location, []))
    holidays = {h.date for h in project.settings.holidays.get(task.completion_location, [])}
    is_complete = task.is_complete

    # The visual end of the bar — extends to today if overdue
    if is_complete:
        bar_end = s.effective_finish
    elif today > s.effective_finish:
        bar_end = today
    else:
        bar_end = s.effective_finish

    for col_idx, d in date_columns:
        is_today_col = (d == today)

        if d < s.computed_start or d > bar_end:
            if is_today_col:
                sheet.write_blank(row_idx, col_idx, None, formats["empty_today"])
            continue

        # Inside bar range
        is_holiday_gap = task.calendar_mode == "working_days" and d in holidays
        is_weekend_gap = (
            task.calendar_mode == "working_days"
            and not is_holiday_gap
            and weekday_code(d) not in work_week
        )
        if is_holiday_gap or is_weekend_gap:
            if is_holiday_gap:
                key = "holiday_gap_today" if is_today_col else "holiday_gap"
            else:
                key = "weekend_gap_today" if is_today_col else "weekend_gap"
            sheet.write_blank(row_idx, col_idx, None, formats[key])
            continue

        # Status segment
        if is_complete:
            status = "completed"
        elif d <= s.computed_finish:
            status = "planned"
        elif d <= s.effective_finish:
            status = "delayed"
        else:  # d <= today, overdue tail
            status = "overdue"

        key = status
        if is_critical and status != "overdue":
            key += "_critical"
        if is_today_col:
            key += "_today"
        sheet.write_blank(row_idx, col_idx, None, formats[key])


def _render_parent_bar_day(sheet, row_idx, date_columns, s, formats,
                           is_critical: bool, today: date) -> None:
    for col_idx, d in date_columns:
        is_today_col = (d == today)
        if d < s.computed_start or d > s.effective_finish:
            if is_today_col:
                sheet.write_blank(row_idx, col_idx, None, formats["empty_today"])
            continue
        key = "parent_critical" if is_critical else "parent"
        if is_today_col:
            key += "_today"
        sheet.write_blank(row_idx, col_idx, None, formats[key])


# -------------------------------------------------------------------------
# Week View

def _build_week_view(workbook, project: Project, schedule, critical_path, formats,
                     axis_start: date, axis_end: date) -> None:
    sheet = workbook.add_worksheet("Week View")
    today = date.today()
    today_week_start = today - timedelta(days=today.weekday())  # Monday of this week
    critical_set = critical_path.critical_task_ids

    # Metadata headers
    for c, h in enumerate(_METADATA_COLS):
        sheet.write(0, c, h, formats["header"])

    week_columns: list[tuple[int, date, date]] = []
    current = axis_start
    col = _METADATA_COL_COUNT
    while current <= axis_end:
        week_end = current + timedelta(days=6)
        text = f"Week of\n{current.isoformat()}"
        is_today_week = (current == today_week_start)
        fmt = formats["header_today"] if is_today_week else formats["header"]
        sheet.write(0, col, text, fmt)
        week_columns.append((col, current, week_end))
        current += timedelta(days=7)
        col += 1

    sheet.set_row(0, 42)
    _set_metadata_column_widths(sheet)
    sheet.set_column(_METADATA_COL_COUNT, col - 1, 12)
    sheet.freeze_panes(1, _METADATA_COL_COUNT)
    sheet.outline_settings(True, False, False, False)

    for row_idx, task in enumerate(_gantt_task_order(project, schedule), start=1):
        level = _hierarchy_level(project, task.id)
        sheet.set_row(row_idx, 30, None, {"level": level} if level > 0 else None)
        _write_task_metadata_row(sheet, row_idx, task, formats, indent=level)
        s = schedule.get(task.id)
        if not s:
            continue

        is_critical = task.id in critical_set
        is_parent = project.has_subtasks(task.id)
        is_complete = task.is_complete

        if is_complete:
            bar_end = s.effective_finish
        elif today > s.effective_finish:
            bar_end = today
        else:
            bar_end = s.effective_finish

        for col_idx, ws, we in week_columns:
            is_today_week = (ws == today_week_start)
            overlap = not (bar_end < ws or s.computed_start > we)

            if not overlap:
                if is_today_week:
                    sheet.write_blank(row_idx, col_idx, None, formats["empty_today"])
                continue

            if is_parent:
                status = "parent"
            elif is_complete:
                status = "completed"
            else:
                # Pick the latest applicable status within the week
                if ws > s.effective_finish:
                    status = "overdue"
                elif ws > s.computed_finish:
                    status = "delayed"
                else:
                    status = "planned"

            key = status
            if is_critical and status != "overdue":
                key += "_critical"
            if is_today_week:
                key += "_today"
            sheet.write_blank(row_idx, col_idx, None, formats[key])


# -------------------------------------------------------------------------
# Schedule Calculations (tabular audit sheet)

def _build_schedule_calculations(workbook, project, schedule, critical_path, formats) -> None:
    sheet = workbook.add_worksheet("Schedule Calculations")

    columns = [
        "TASK ID", "Name", "Hierarchy Level", "Parent ID", "Location", "Calendar Mode",
        "Cycle Time (Days)", "Manual Start Date", "Baseline Start", "Baseline Finish",
        "Computed Start", "Computed Finish",
        "Delay Days", "Effective Finish", "Actual Completion Date", "Is Complete",
        "Dependencies", "Total Float", "Is Critical", "Was On Critical Path",
        "Downstream Impact", "Validation Warnings",
    ]
    for col, header in enumerate(columns):
        sheet.write(0, col, header, formats["header"])

    history_map = {h.task_id: h.was_on_critical_path for h in project.project.history}

    for row_idx, task in enumerate(project.tasks, start=1):
        s = schedule.get(task.id)
        level = _hierarchy_level(project, task.id)
        deps_str = "; ".join(f"{d.id}[{d.type}, lag {d.lag_days}]" for d in task.dependencies)
        downstream = sum(1 for other in project.tasks for d in other.dependencies if d.id == task.id)

        sheet.write(row_idx, 0, task.id)
        sheet.write(row_idx, 1, task.name)
        sheet.write(row_idx, 2, level)
        sheet.write(row_idx, 3, task.parent_id or "")
        sheet.write(row_idx, 4, task.completion_location)
        sheet.write(row_idx, 5, task.calendar_mode)
        sheet.write(row_idx, 6, task.cycle_time_days if task.cycle_time_days is not None else "")
        sheet.write(row_idx, 7, task.manual_start_date.isoformat() if task.manual_start_date else "")
        sheet.write(row_idx, 8, task.baseline_start.isoformat() if task.baseline_start else "")
        sheet.write(row_idx, 9, task.baseline_finish.isoformat() if task.baseline_finish else "")
        sheet.write(row_idx, 10, s.computed_start.isoformat() if s else "")
        sheet.write(row_idx, 11, s.computed_finish.isoformat() if s else "")
        sheet.write(row_idx, 12, task.delay_days)
        sheet.write(row_idx, 13, s.effective_finish.isoformat() if s else "")
        sheet.write(row_idx, 14, task.actual_completion_date.isoformat() if task.actual_completion_date else "")
        sheet.write(row_idx, 15, task.is_complete)
        sheet.write(row_idx, 16, deps_str)
        sheet.write(row_idx, 17, critical_path.total_float.get(task.id, 0))
        sheet.write(row_idx, 18, task.id in critical_path.critical_task_ids)
        sheet.write(row_idx, 19, history_map.get(task.id, False))
        sheet.write(row_idx, 20, downstream)
        sheet.write(row_idx, 21, "")

    sheet.freeze_panes(1, 2)
    schedule_widths = [
        12, 36, 16, 12, 12, 16, 18, 18, 16, 16, 16, 16,
        12, 16, 22, 12, 34, 12, 12, 20, 18, 34,
    ]
    for col, width in enumerate(schedule_widths):
        sheet.set_column(col, col, width, formats["calc_cell"])
    for row_idx in range(1, len(project.tasks) + 1):
        sheet.set_row(row_idx, 24)


# -------------------------------------------------------------------------
# Critical Path Notes

def _build_critical_path_notes(workbook, project, schedule, critical_path, formats) -> None:
    sheet = workbook.add_worksheet("Critical Path Notes")

    overdue = [t.id for t in project.tasks
               if not t.is_complete
               and t.id in schedule
               and schedule[t.id].effective_finish < date.today()]
    delayed = [t.id for t in project.tasks if t.delay_days > 0 and not t.is_complete]

    rows = [
        ("Project", f"{project.project.id} — {project.project.name}"),
        ("Project end (derived)", critical_path.project_end.isoformat() if critical_path.project_end else "n/a"),
        ("Total tasks", len(project.tasks)),
        ("Critical path tasks", len(critical_path.critical_task_ids)),
        ("Overdue incomplete tasks", len(overdue)),
        ("Tasks with delay > 0", len(delayed)),
        ("", ""),
        ("Summary", _build_summary(project, schedule, critical_path, overdue, delayed)),
    ]
    for row_idx, (label, value) in enumerate(rows):
        sheet.write(row_idx, 0, label, formats["summary_label"] if label else None)
        sheet.write(row_idx, 1, value, formats["summary_value"])
        sheet.set_row(row_idx, 24)

    sheet.set_column(0, 0, 28)
    sheet.set_column(1, 1, 110)


def _build_summary(project, schedule, critical_path, overdue, delayed) -> str:
    end = critical_path.project_end.isoformat() if critical_path.project_end else "tbd"
    return (
        f"Project {project.project.id} ends {end}. "
        f"{len(critical_path.critical_task_ids)} tasks on critical path. "
        f"{len(overdue)} overdue. {len(delayed)} delayed."
    )


# -------------------------------------------------------------------------
# Chart Key & Info (reference / legend sheet)

def _build_chart_key_info(workbook, project: Project, formats) -> None:
    """Reference sheet documenting work-week per location and the color legend."""
    from .locations import LOCATION_DISPLAY

    sheet = workbook.add_worksheet("Chart Key & Info")

    title_fmt = workbook.add_format({
        "bold": True, "font_size": 14, "align": "left", "valign": "vcenter",
        "text_wrap": True,
    })
    section_fmt = workbook.add_format({
        "bold": True, "font_size": 11, "bg_color": _C_HEADER,
        "border": 1, "align": "left", "valign": "vcenter", "text_wrap": True,
    })
    body_fmt = workbook.add_format({
        "border": 1, "align": "left", "valign": "top", "text_wrap": True,
    })
    body_bold_fmt = workbook.add_format({
        "border": 1, "align": "left", "valign": "top", "bold": True, "text_wrap": True,
    })

    sheet.set_column(0, 0, 26)    # Sample / Code
    sheet.set_column(1, 1, 36)    # Site / Color
    sheet.set_column(2, 2, 118)   # Description

    row = 0
    sheet.set_row(row, 25)
    sheet.merge_range(row, 0, row, 2, "PMSuite Gantt Chart — Key & Info", title_fmt)
    row += 2

    # -- Working Weeks by Location ---------------------------------------
    sheet.merge_range(row, 0, row, 2, "Working Weeks by Location", section_fmt)
    row += 1
    sheet.write(row, 0, "Code", body_bold_fmt)
    sheet.write(row, 1, "Site", body_bold_fmt)
    sheet.write(row, 2, "Working Days (USA-perspective)", body_bold_fmt)
    row += 1

    weekday_names = {
        "MON": "Mon", "TUE": "Tue", "WED": "Wed", "THU": "Thu",
        "FRI": "Fri", "SAT": "Sat", "SUN": "Sun",
    }

    # Iterate the project's work_weeks so we only show locations actually used
    for code in sorted(project.settings.work_weeks.keys()):
        days = project.settings.work_weeks[code]
        days_str = ", ".join(weekday_names.get(d, d) for d in days)
        sheet.write(row, 0, code, body_fmt)
        sheet.write(row, 1, LOCATION_DISPLAY.get(code, code), body_fmt)
        sheet.write(row, 2, days_str, body_fmt)
        row += 1

    row += 1

    # -- Color Legend ----------------------------------------------------
    sheet.merge_range(row, 0, row, 2, "Color Legend (Gantt bar segments)", section_fmt)
    row += 1
    sheet.write(row, 0, "Sample", body_bold_fmt)
    sheet.write(row, 1, "Name", body_bold_fmt)
    sheet.write(row, 2, "Meaning", body_bold_fmt)
    row += 1

    legend = [
        ("planned",   "Planned (pale blue)",
         "An in-progress task during its scheduled cycle (computed_start to computed_finish)."),
        ("completed", "Completed (green)",
         "A task marked is_complete. The entire bar shows as completed regardless of segment."),
        ("delayed",   "Delay extension (orange)",
         "Days added by cumulative delay_days beyond computed_finish, up to effective_finish."),
        ("overdue",   "Overdue tail (red)",
         "Days from effective_finish to today on an incomplete task that should have been done already."),
        ("parent",    "Parent summary (dark gray)",
         "A rolled-up parent task's span across all of its descendants."),
        ("weekend_gap", "Weekend gap (light gray)",
         "Inside a working-day task's bar, days that are not part of that location's work-week."),
        ("holiday_gap", "Holiday gap (darker gray)",
         "Inside a working-day task's bar, days that fall on a location-specific holiday."),
        ("empty_today", "Today line (yellow)",
         "The column for today's date is marked across every row with a thick black left border."),
    ]
    for key, name, description in legend:
        sheet.write_blank(row, 0, None, formats[key])
        sheet.write(row, 1, name, body_fmt)
        sheet.write(row, 2, description, body_fmt)
        sheet.set_row(row, 22)
        row += 1

    row += 1

    # -- Critical Path indicator -----------------------------------------
    sheet.merge_range(row, 0, row, 2, "Critical Path Indicator", section_fmt)
    row += 1
    sheet.write(row, 0, "Sample", body_bold_fmt)
    sheet.write(row, 1, "Name", body_bold_fmt)
    sheet.write(row, 2, "Meaning", body_bold_fmt)
    row += 1

    sheet.write_blank(row, 0, None, formats["planned_critical"])
    sheet.write(row, 1, "Critical-path stripe (dark red border)", body_fmt)
    sheet.write(row, 2,
                "Tasks on the project's critical path show a dark red top + bottom border "
                "on every bar cell. These are the 'long pole' tasks driving the project end date — "
                "any slip on a critical task pushes the project end. Tasks with parallel chains "
                "of shorter cycle time are NOT critical; only the longest path through the "
                "dependency graph is marked.",
                body_fmt)
    sheet.set_row(row, 60)
    row += 2

    # -- Task row order --------------------------------------------------
    sheet.merge_range(row, 0, row, 2, "Task Row Order", section_fmt)
    row += 1
    sheet.write(row, 0, "Day / Week View rows", body_bold_fmt)
    sheet.write(row, 1, "Chronological", body_fmt)
    sheet.write(
        row, 2,
        "Rows in the Day View and Week View are sorted by scheduled start and finish dates, "
        "not by task ID. Task IDs remain stable creation identifiers: a later-created TASK-013 "
        "can appear between TASK-009 and TASK-010 when its computed schedule belongs there.",
        body_fmt,
    )
    sheet.set_row(row, 48)
    row += 2

    # -- Reading the frozen pane -----------------------------------------
    sheet.merge_range(row, 0, row, 2, "Reading the Frozen Pane (Day View / Week View)", section_fmt)
    row += 1
    sheet.write(row, 0, "Column", body_bold_fmt)
    sheet.write(row, 1, "Type", body_bold_fmt)
    sheet.write(row, 2, "Meaning", body_bold_fmt)
    row += 1

    pane_rows = [
        ("TASK ID",            "System-generated", "Stable sequential identifier (TASK-NNN). Never reused, gaps allowed."),
        ("Name",               "User-supplied",    "Free-form task name. May change without breaking dependencies."),
        ("Location",           "Code",             "Site code (e.g., DAL, MLA, TAI). See Working Weeks section."),
        ("Cycle Time (Days)",  "Integer",          "Inclusive task duration in the task's calendar mode (e_days or working_days)."),
        ("Baseline Start",     "Date",             "The user-committed planned start. Does not shift with delays — for variance reporting."),
        ("Baseline Finish",    "Date",             "The user-committed planned finish. Pair with Baseline Start to track plan vs actual."),
        ("Dependencies",       "ID list",          "Numerical task IDs that must complete before this task starts. e.g., '003, 007' = depends on TASK-003 and TASK-007."),
    ]
    for col_name, kind, description in pane_rows:
        sheet.write(row, 0, col_name, body_fmt)
        sheet.write(row, 1, kind, body_fmt)
        sheet.write(row, 2, description, body_fmt)
        row += 1


def _hierarchy_level(project: Project, task_id: str) -> int:
    """0 = root, 1 = first-level child, etc."""
    level = 0
    current = project.task_by_id(task_id)
    while current and current.parent_id:
        level += 1
        current = project.task_by_id(current.parent_id)
        if level > 100:
            return level
    return level
