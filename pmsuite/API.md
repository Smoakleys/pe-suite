# API — PMSuite Gantt Builder

The public Python API for PMSuite. Streamlit and any other consumer should use only what's documented here.

For data shape, see [JSONFILE.md](JSONFILE.md). For the full design rationale, [DESIGN.md](DESIGN.md). For the decision log behind these choices, [MASTERECAP.md](MASTERECAP.md).

## Import

```python
from gantt_builder import api
from gantt_builder.models import Project, Task, Dependency, Settings
from gantt_builder.errors import (
    GanttError, ValidationFailure, StructuralError,
    CircularDependencyError, MissingDependencyError, DuplicateTaskIdError,
    SelfDependencyError, InvalidParentRelationshipError, InvalidCycleTimeError,
    InvalidCompletionDateError, UnanchoredTaskError, InvalidLocationError,
    MissingHolidayDataError, InvalidDelayDaysError, ParentHasCycleTimeError,
)
```

The public API surface is `gantt_builder.api`. The `models` module exposes pydantic types for typed callers. The `errors` module exposes the exception hierarchy.

## Public functions

### `load_project(path) -> Project`

Load a project from a JSON file.

```python
project = api.load_project("projects/program_x.json")
```

**Parameters:**
- `path: str | Path` — Path to the JSON file.

**Returns:** `Project` instance.

**Raises:**
- `StructuralError` — file missing, malformed JSON, or schema violation.

**Side effects:** writes a log entry to `.logs/gantt_builder.log`. Does not mutate disk.

---

### `save_project(project, path) -> None`

Atomically write the project JSON to disk.

```python
api.save_project(project, "projects/program_x.json")
```

**Parameters:**
- `project: Project` — In-memory project instance.
- `path: str | Path` — Destination path.

**Side effects:**
- Updates `project.project.updated_at` to current time before writing.
- Writes to `<path>.tmp` then `os.replace` to the final path (atomic).
- If `project.settings.keep_local_snapshots > 0`, writes a rotating snapshot under `<path>.parent/.backups/<project_id>/<project_id>_<timestamp>.json`. Prunes oldest beyond the configured limit.

**Raises:** Any `OSError` from the filesystem; cleans up the temp file on failure.

---

### `validate_project(project) -> list[str]`

Run logical-tier validation.

```python
warnings = api.validate_project(project)
for w in warnings:
    print(f"warning: {w}")
```

**Returns:** A list of non-fatal warning strings (may be empty).

**Raises:** `ValidationFailure` if any logical-tier errors are detected. The raised exception contains a list of `GanttError` subclass instances in `exc.errors`. Use `.to_envelope()` on each to serialize.

**Tier 1** structural validation (malformed JSON, missing required fields, schema-level type errors) happens at `load_project` time as `StructuralError`. Tier 2 logical validation happens here.

**Logical validators run:**
- Duplicate task IDs
- Task `completion_location` not in the 8-location enum
- Missing holiday/work_week entry for a referenced location
- Self-dependencies (task depends on itself)
- Missing dependency references (depends on unknown task ID)
- Circular dependencies (DFS-detected)
- Invalid parent relationships (parent_id references unknown task; or task is its own parent)
- Parent task has `cycle_time_days` set (forbidden — parents derive duration from children)
- Leaf task missing or invalid `cycle_time_days`
- Unanchored leaf task (no dependencies AND no `manual_start_date`)
- `is_complete: true` with `actual_completion_date: null`
- `is_complete: false` with `actual_completion_date` set
- Negative `delay_days`

Save operations do NOT call this internally — the user can save a logically-invalid project (e.g., during a multi-step edit). Build operations DO call this internally and re-raise `ValidationFailure` if it fails.

---

### `schedule_project(project) -> dict[str, ScheduledTask]`

Run the forward-pass scheduler.

```python
schedule = api.schedule_project(project)
for task_id, s in schedule.items():
    print(f"{task_id}: {s.computed_start} → {s.effective_finish}")
```

**Returns:** A dict keyed by task ID. Each value is a `ScheduledTask` dataclass:

```python
@dataclass
class ScheduledTask:
    task_id: str
    computed_start: date
    computed_finish: date
    effective_finish: date  # computed_finish + delay_days, OR actual_completion_date if complete
```

Includes both leaf tasks and parent rollups. Parent values are derived from descendants: `start = min(child starts)`, `finish = max(child finishes)`, `effective_finish = max(child effective_finishes)`.

**Current behavior:** FS / SS / FF / SF dependencies are supported with positive/negative lag counted in the predecessor's calendar mode. Parent manual starts and parent dependencies are inherited by descendant leaves, and dependencies on parent predecessors use the parent's rolled-up descendant schedule. Backward-pass float and long-pole critical-path display are implemented in `critical_path.py`.

**Raises:** `StructuralError` if a task is unanchored or has invalid cycle time. Validation should catch these first; this is a safety net.

---

### `build_excel(project, output_dir=None) -> Path`

Validate, schedule, and write the Excel workbook.

```python
output_path = api.build_excel(project)
# or
output_path = api.build_excel(project, output_dir="custom/output/dir")
```

**Parameters:**
- `project: Project` — In-memory project instance.
- `output_dir: str | Path | None` — Override for output directory. If `None`, uses `project.settings.output_directory` (default `"output"`).

**Returns:** `Path` to the generated `.xlsx` file.

**Side effects:**
- Runs `validate_project()` first; raises `ValidationFailure` if logical errors.
- Computes the schedule.
- Writes a workbook to `<output_dir>/gantt_<project_id>_<YYYY-MM-DD>_<HHMMSS>.xlsx`.
- Updates `project.project.last_export = LastExport(path=..., at=...)`. **This mutates the project object.** Caller may want to `save_project` after to persist the audit trail.
- Collision-safe with `_2`, `_3` suffixes on rare same-second collisions.

**Raises:** `ValidationFailure` (re-raised from validation). Any file-system error from xlsxwriter.

For the full Excel output specification, see [EXCELBUILDER.md](EXCELBUILDER.md). The workbook currently contains Chart Key & Info, Day View, Week View, Schedule Calculations, and Critical Path Notes.

Day View and Week View rows are rendered in chronological schedule order. Stable `TASK-NNN` IDs are not renumbered and do not imply row position.

---

## Error envelope

All `GanttError` subclasses serialize to a structured envelope for transport across the UI boundary.

### Single-error envelope

```python
err = CircularDependencyError(
    "Circular dependency detected: TASK-001 -> TASK-002 -> TASK-001.",
    affected_tasks=["TASK-001", "TASK-002"],
)
err.to_envelope()
# {
#   "success": False,
#   "error_code": "CIRCULAR_DEPENDENCY",
#   "message": "Circular dependency detected: TASK-001 -> TASK-002 -> TASK-001.",
#   "affected_tasks": ["TASK-001", "TASK-002"],
# }
```

### Multi-error envelope (ValidationFailure)

```python
try:
    api.validate_project(project)
except ValidationFailure as exc:
    exc.to_envelope()
    # {
    #   "success": False,
    #   "errors": [
    #     {"success": False, "error_code": "DUPLICATE_TASK_ID", ...},
    #     {"success": False, "error_code": "MISSING_DEPENDENCY", ...},
    #     ...
    #   ],
    # }
```

`ValidationFailure.errors` is a `list[GanttError]` that the UI can iterate to display each error individually.

## Exception hierarchy

```
GanttError                          (base; error_code = "GANTT_ERROR")
├── ValidationFailure               ("VALIDATION_FAILURE")    — collects multiple
├── StructuralError                 ("STRUCTURAL_ERROR")      — tier 1, fails fast
├── CircularDependencyError         ("CIRCULAR_DEPENDENCY")
├── MissingDependencyError          ("MISSING_DEPENDENCY")
├── DuplicateTaskIdError            ("DUPLICATE_TASK_ID")
├── SelfDependencyError             ("SELF_DEPENDENCY")
├── InvalidParentRelationshipError  ("INVALID_PARENT_RELATIONSHIP")
├── InvalidCycleTimeError           ("INVALID_CYCLE_TIME")
├── InvalidStartDateError           ("INVALID_START_DATE")
├── InvalidCompletionDateError      ("INVALID_COMPLETION_DATE")
├── UnanchoredTaskError             ("UNANCHORED_TASK")
├── InvalidLocationError            ("INVALID_LOCATION")
├── MissingHolidayDataError         ("MISSING_HOLIDAY_DATA")
├── InvalidDelayDaysError           ("INVALID_DELAY_DAYS")
├── ParentHasCycleTimeError         ("PARENT_HAS_CYCLE_TIME")
├── TaskNotFoundError               ("TASK_NOT_FOUND")
├── CompletedTaskCannotBeDelayedError ("COMPLETED_TASK_CANNOT_BE_DELAYED")
└── TaskDeletionBlockedError        ("TASK_DELETION_BLOCKED")
```

Every subclass carries:
- `error_code: str` (class attribute)
- `message: str`
- `affected_tasks: list[str]`

## Streamlit usage pattern

```python
import streamlit as st
from gantt_builder import api
from gantt_builder.errors import GanttError, ValidationFailure

try:
    output = api.build_excel(project)
    st.success(f"Built: {output}")
except ValidationFailure as exc:
    for err in exc.errors:
        st.error(f"{err.error_code}: {err.message}")
        if err.affected_tasks:
            st.caption(f"Affected: {', '.join(err.affected_tasks)}")
except GanttError as exc:
    st.error(f"{exc.error_code}: {exc.message}")
```

## Logging

`gantt_builder.logging_config.configure_logging()` is called automatically on first use of any API function. Configuration is idempotent. Logs go to:

- `.logs/gantt_builder.log` — rotating file, 10 MB, last 5 retained, UTF-8.
- `stderr` — same content.

Default level `INFO`. Module-level loggers via `get_logger(__name__)`.

## Delay engine

### `preview_auto_catchup(project, today=None) -> DelayApplicationResult`

Dry-run. Computes per-task overdue days without mutating the project. UI uses this to populate the auto-catchup prompt modal.

### `apply_auto_catchup(project, today=None) -> DelayApplicationResult`

Per-task accurate catch-up (Option B per DESIGN.md Q11). For each incomplete leaf, adds `max(0, today - effective_finish)` to `delay_days` and appends a `DelayLogEntry`. Updates `settings.last_auto_delay_run`. Idempotent within a single day. Fresh projects (no prior run) initialize baseline to today without applying delays.

### `apply_manual_delay(project, task_id, days_added, reason=None, today=None) -> DelayApplicationResult`

User-driven delay. Raises `CompletedTaskCannotBeDelayedError` if the task is already complete (delays are frozen on completion). Raises `TaskNotFoundError` if the ID is unknown. Raises `ValueError` if `days_added < 1`.

### `undo_delay_batch(project, result) -> list[str]`

Reverses a `DelayApplicationResult` within the session. Returns the list of task IDs successfully reverted. Tasks whose `delay_log` has been manually edited between apply and undo are skipped — caller can detect skips by comparing `len(returned) < len(batch.entries)`.

### `is_auto_catchup_pending(project, today=None) -> bool`

Cheap check used by Streamlit on load to decide whether to show the auto-catchup prompt.

## Completion

### `mark_task_complete(project, task_id, completion_date=None) -> CompletionResult`

Marks the task complete. If the task has descendants (any depth), cascades `is_complete=True` and `actual_completion_date` down through every descendant.

**Cascade rules (Q8d common-sense reading):**
- Descendant not yet complete → marked with `completion_date`.
- Descendant complete with EARLIER date → preserved (don't destroy history).
- Descendant complete with LATER date → overwritten to `completion_date`.
- Descendant complete with SAME date → no change recorded.

Returns a `CompletionResult` with `primary_task_id`, `applied_date`, `changes` (the audit list), and `preserved` (task IDs of children kept with their earlier date).

Raises `TaskNotFoundError` if `task_id` is unknown.

### `unmark_task_complete(project, task_id) -> None`

Toggles `is_complete: true → false` on ONE task. Clears `actual_completion_date`. Does NOT cascade to descendants — if needed, use `undo_complete_batch` with the original `CompletionResult` to revert a full cascade.

### `undo_complete_batch(project, result) -> list[str]`

Reverses a mark-complete batch. Each task is restored to its `prev_*` snapshot only if its current state still matches the `new_*` snapshot we wrote (defensive: don't clobber subsequent manual edits).

## Baseline

### `set_project_baseline(project, overwrite=False) -> BaselineResult`

Snapshots current `computed_start` / `computed_finish` into each task's `baseline_start` / `baseline_finish`. By default, tasks that already have a baseline are skipped. Pass `overwrite=True` to re-baseline every task. Returns a `BaselineResult` listing baselined and skipped task IDs.

The baseline is the user-committed plan reference — it does NOT move when delays or completion shift the live schedule. Used by Excel rendering to display "Baseline Start" / "Baseline Finish" alongside "Computed Start" / "Computed Finish" in both the frozen pane of Day View / Week View and the Schedule Calculations audit sheet.

## Editing

### `add_task(project, **kwargs) -> Task`

Appends a new task with the next available generated `TASK-NNN` ID. If `settings.next_task_id` is stale, existing IDs are skipped and the counter is advanced to the next unused value. Task IDs cannot be supplied by callers.

### `update_task(project, task_id, **kwargs) -> Task`

Updates one task after validating the resulting `Task` model. Task IDs are stable and cannot be renamed.

### `delete_task(project, task_id) -> None`

Deletes a task only when no other task depends on it and it has no child tasks. Raises `TaskDeletionBlockedError` with affected task IDs when deletion would break dependencies or hierarchy.

### `add_dependency(project, task_id, dep_id, type="FS", lag_days=0) -> None`

Adds or updates a predecessor dependency. Rejects unknown tasks, self-dependencies, and dependencies that conflict with the parent hierarchy.

### `remove_dependency(project, task_id, dep_id) -> None`

Removes a predecessor dependency from a task. No-op when the edge is already absent.

## What's NOT in the public API yet (planned for later Step 6/7 work)

- `reseed_holidays(project, location) -> HolidayDiff` — Q20 re-seed-with-diff (currently `seed_holidays()` in `locations.py` returns the raw library output; the diff wrapper is the Streamlit-side need).
- `update_holidays(project, location, holidays) -> None`.

Direct model mutations should be followed by `save_project()` to persist and `validate_project()` to verify.
