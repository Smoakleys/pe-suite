# JSONFILE — Project File Schema

The JSON project file is the source of truth for PMSuite. The Streamlit UI is a thin client over the API; the Excel workbook is a derived artifact. **All authoritative data lives here.**

For the API that mutates this file, see [API.md](API.md). For the architectural rationale, [DESIGN.md](DESIGN.md). For the decision log behind each field, [MASTERECAP.md](MASTERECAP.md).

## Top-level structure

```jsonc
{
  "project":  { ... },     // metadata block
  "settings": { ... },     // configuration block
  "tasks":    [ ... ]      // array of tasks
}
```

Canonical serialization always includes every defined field with its explicit default — no field is omitted. This produces predictable diffs in version control and clean visual scanning. Pydantic emits via `model_dump(mode="json", exclude_defaults=False, exclude_none=False)`.

## `project` block

```jsonc
{
  "id":          "PROGRAM-001",                  // required string
  "name":        "Example Program",              // required string
  "timezone":    "America/Chicago",              // IANA tz; default America/Chicago
  "created_at":  "2026-05-13T12:00:00-05:00",    // ISO 8601 with tz; system-managed
  "updated_at":  "2026-05-13T17:30:00-05:00",    // ISO 8601 with tz; system-managed
  "last_export": null | {
    "path": "output/gantt_PROGRAM-001_2026-05-13_142205.xlsx",
    "at":   "2026-05-13T14:22:05-05:00"
  },
  "history": [
    {
      "task_id":               "TASK-042",
      "was_on_critical_path":  true,
      "captured_at":           "2026-05-13T11:00:00-05:00"
    }
  ]
}
```

### Field reference

| Field        | Type                          | Required | Default              | Notes |
|--------------|-------------------------------|----------|----------------------|-------|
| `id`         | string                        | yes      | —                    | Validated `^[A-Z][A-Z0-9-]+$`. Used in output filenames. |
| `name`       | string                        | yes      | —                    | User-friendly project name. |
| `timezone`   | string                        | yes      | `"America/Chicago"`  | IANA timezone name. Used for filename timestamps and audit metadata. |
| `created_at` | ISO 8601 datetime with tz     | yes      | system-set           | Never user-edited. |
| `updated_at` | ISO 8601 datetime with tz     | yes      | system-set           | Updated on every save. |
| `last_export`| object \| null                | no       | `null`               | Set by `build_excel()`; tracks most recent output file. |
| `history`    | array of HistoryEntry         | no       | `[]`                 | Snapshot of derived facts (e.g., `was_on_critical_path`) at the moment of task completion. |

## `settings` block

```jsonc
{
  "holidays": {
      "DAL":    [ { "date": "2026-07-04", "name": "Independence Day", "source": "seeded" } ],
    "MLA":    [ { "date": "2026-08-31", "name": "Hari Kebangsaan", "source": "seeded" } ],
    "CLARK":  [],
    "TIPI":   [],
    "TAI":    [],
    "TIEMA":  [],
    "FR-BIP": [],
    "AIZU":   []
  },
  "work_weeks": {
    "DAL":    ["MON", "TUE", "WED", "THU", "FRI"],
    "FR-BIP": ["MON", "TUE", "WED", "THU", "FRI"],
    "MLA":    ["SUN", "MON", "TUE", "WED", "THU"],
    "TIEMA":  ["SUN", "MON", "TUE", "WED", "THU"],
    "CLARK":  ["SUN", "MON", "TUE", "WED", "THU"],
    "TIPI":   ["SUN", "MON", "TUE", "WED", "THU"],
    "TAI":    ["SUN", "MON", "TUE", "WED", "THU"],
    "AIZU":   ["SUN", "MON", "TUE", "WED", "THU"]
  },
  "next_task_id":          8,
  "output_directory":      "output",
  "keep_local_snapshots":  10,
  "auto_delay_on_load":    true,
  "last_auto_delay_run":   "2026-05-13",
  "date_axis_start":       null,
  "date_axis_end":         null
}
```

### Field reference

| Field                  | Type                                      | Required | Default     | Notes |
|------------------------|-------------------------------------------|----------|-------------|-------|
| `holidays`             | `dict[str, list[HolidayEntry]]`           | yes      | `{}`        | Must include a key for every location referenced by tasks. Empty list `[]` is valid. |
| `work_weeks`           | `dict[str, list[str]]`                    | yes      | `{}`        | Weekday codes `"MON"`–`"SUN"`. Must include a key for every location referenced. |
| `next_task_id`         | int                                       | yes      | `1`         | Counter for generating next `TASK-NNN` ID. Gaps allowed, never reused. |
| `output_directory`     | string                                    | no       | `"output"`  | Relative or absolute path for generated Excel files. |
| `keep_local_snapshots` | int                                       | no       | `10`        | Rotating snapshots in `projects/.backups/`. Set 0 to disable. |
| `auto_delay_on_load`   | bool                                      | no       | `true`      | If true, prompts to apply auto-catchup on project load. |
| `last_auto_delay_run`  | ISO date string \| null                   | no       | `null`      | Last successful auto-delay sweep. Idempotency key. Set on first save without applying delays. |
| `date_axis_start`      | ISO date string \| null                   | no       | `null`      | Override for Excel axis. Auto-derived if `null`. |
| `date_axis_end`        | ISO date string \| null                   | no       | `null`      | Override for Excel axis. Auto-derived if `null`. |

### Validation rules for settings

- Every location used by any task must have an entry in both `holidays` and `work_weeks`. Missing entries raise `MissingHolidayDataError`.
- Locations must be from the 8-element v1 enum: `DAL`, `FR-BIP`, `MLA`, `TIEMA`, `CLARK`, `TIPI`, `TAI`, `AIZU`.

## `tasks` array

Each entry is a task. Tasks reference each other by ID for dependencies and parent relationships.

### Task object

```jsonc
{
  "id":                      "TASK-001",
  "name":                    "Wafer fab",
  "completion_location":     "TAI",
  "calendar_mode":           "e_days",
  "cycle_time_days":         21,
  "manual_start_date":       "2026-05-18",
  "baseline_start":          "2026-05-18",
  "baseline_finish":         "2026-06-07",
  "dependencies":            [ { "id": "TASK-000", "type": "FS", "lag_days": 0 } ],
  "parent_id":               null,
  "is_complete":             false,
  "actual_completion_date":  null,
  "delay_days":              0,
  "delay_log":               []
}
```

### Field reference

| Field                    | Type                                     | Required | Default | Notes |
|--------------------------|------------------------------------------|----------|---------|-------|
| `id`                     | string                                   | yes      | —       | System-generated `TASK-NNN`. Never user-edited. Sequential, gaps allowed, never reused. Does not control Excel Gantt row order; Day View / Week View rows sort chronologically by scheduled dates. |
| `name`                   | string                                   | yes      | —       | User-provided. May change without breaking dependencies (IDs are stable). |
| `completion_location`    | enum                                     | yes      | —       | One of: `DAL`, `FR-BIP`, `MLA`, `TIEMA`, `CLARK`, `TIPI`, `TAI`, `AIZU`. |
| `calendar_mode`          | `"working_days" \| "e_days"`             | yes      | —       | `e_days` counts every calendar day (e.g., oven cycles). `working_days` counts only the location's working-week minus its holidays. |
| `cycle_time_days`        | int \| null                              | yes if leaf, MUST be null if parent | —     | Inclusive. Minimum 1 for leaves. Parents derive duration from children — `cycle_time_days` MUST be unset for parents (else `ParentHasCycleTimeError`). Excel column header: **"Cycle Time (Days)"**. |
| `manual_start_date`      | ISO date string \| null                  | required for leaves with no dependencies, otherwise optional | `null` | Acts as a **floor** when present. Combined with dependency-driven starts via max. |
| `baseline_start`         | ISO date string \| null                  | no       | `null`  | The user-committed planned start, captured via `set_project_baseline()`. Does NOT shift with delays or completion — represents the original plan for variance reporting. None means baseline not yet set. |
| `baseline_finish`        | ISO date string \| null                  | no       | `null`  | Symmetric to `baseline_start` — the user-committed planned finish. |
| `dependencies`           | array of Dependency (object or string)   | no       | `[]`    | Bare string shorthand `["TASK-001"]` accepted; normalized to object form on load. |
| `parent_id`              | string \| null                           | no       | `null`  | Must reference an existing task ID. No cycles allowed. |
| `is_complete`            | bool                                     | no       | `false` | If `true`, `actual_completion_date` is required. |
| `actual_completion_date` | ISO date string \| null                  | required when `is_complete: true` | `null` | UI auto-fills today's date when checkbox flips on. |
| `delay_days`             | int                                      | no       | `0`     | Cumulative. Non-negative. Added to `computed_finish` to produce `effective_finish` (in task's calendar mode). |
| `delay_log`              | array of DelayLogEntry                   | no       | `[]`    | Audit trail. Scheduler reads sum; UI/Excel read this for history. |

### Dependency object

```jsonc
{
  "id":       "TASK-001",
  "type":     "FS",          // FS | SS | FF | SF
  "lag_days": 0              // positive = delay, negative = lead
}
```

| Field      | Type                                | Default | Notes |
|------------|-------------------------------------|---------|-------|
| `id`       | string                              | —       | Must reference an existing task ID. |
| `type`     | `"FS" \| "SS" \| "FF" \| "SF"`     | `"FS"`  | FS = Finish-to-Start (default). See [DESIGN.md §8](DESIGN.md). |
| `lag_days` | int                                 | `0`     | Counted in **predecessor's** calendar mode. Negative = lead time. |

FS / SS / FF / SF are supported. `lag_days` is counted in the predecessor's calendar mode, then the successor resolves in its own calendar mode.

### Bare string shorthand

```jsonc
"dependencies": [ "TASK-001", "TASK-002" ]
```

…is normalized on load to:

```jsonc
"dependencies": [
  { "id": "TASK-001", "type": "FS", "lag_days": 0 },
  { "id": "TASK-002", "type": "FS", "lag_days": 0 }
]
```

Saving always emits the canonical object form.

### HolidayEntry object

```jsonc
{
  "date":   "2026-07-04",
  "name":   "Independence Day",
  "source": "seeded"            // seeded | user-added | user-edited
}
```

| Field    | Type                                          | Notes |
|----------|-----------------------------------------------|-------|
| `date`   | ISO date string                               | Stored as **local date** to the location (not USA-perspective-shifted). |
| `name`   | string                                        | Shown in Excel column headers and UI tooltips. |
| `source` | `"seeded" \| "user-added" \| "user-edited"`   | Used by the re-seed-from-library diff to detect user edits and avoid silent overwrites. |

### DelayLogEntry object

```jsonc
{
  "date":       "2026-05-13",
  "source":     "auto",           // manual | auto
  "days_added": 3,
  "reason":     "auto-catchup since 2026-05-10"
}
```

| Field        | Type                          | Notes |
|--------------|-------------------------------|-------|
| `date`       | ISO date string               | When the delay entry was added. |
| `source`     | `"manual" \| "auto"`          | Tells the UI whether to show "user-applied" or "auto-applied" tag. |
| `days_added` | int                           | Increment to `delay_days`. Always positive. |
| `reason`     | string \| null (optional)     | Free-form. The auto-catchup entry uses `"auto-catchup since <last_run_date>"`. |

### HistoryEntry object (in `project.history`)

```jsonc
{
  "task_id":              "TASK-042",
  "was_on_critical_path": true,
  "captured_at":          "2026-05-13T11:00:00-05:00"
}
```

Snapshot captured at the moment a task is marked complete, preserving derived facts that would otherwise be lost.

## Derived fields (NEVER stored in JSON)

These are computed at runtime from the stored data. If you see them in a JSON file, something is wrong:

- `has_subtasks` — derived from `parent_id` references.
- `computed_start`, `computed_finish` — scheduler output.
- `effective_finish` — `computed_finish + delay_days` (in task's calendar mode), OR `actual_completion_date` if complete.
- `total_float`, `is_critical` — CPM backward-pass output.
- `is_overdue` — `today > effective_finish && !is_complete`.
- `hierarchy_level` — depth in the parent tree.

## Minimal valid project (smallest schema-valid file)

```jsonc
{
  "project": {
    "id":         "MIN-001",
    "name":       "Minimal",
    "timezone":   "America/Chicago",
    "created_at": "2026-05-13T12:00:00-05:00",
    "updated_at": "2026-05-13T12:00:00-05:00",
    "last_export": null,
    "history":     []
  },
  "settings": {
    "holidays":             { "DAL": [] },
    "work_weeks":           { "DAL": ["MON","TUE","WED","THU","FRI"] },
    "next_task_id":         2,
    "output_directory":     "output",
    "keep_local_snapshots": 10,
    "auto_delay_on_load":   true,
    "last_auto_delay_run":  null,
    "date_axis_start":      null,
    "date_axis_end":        null
  },
  "tasks": [
    {
      "id":                     "TASK-001",
      "name":                   "First task",
      "completion_location":    "DAL",
      "calendar_mode":          "e_days",
      "cycle_time_days":        1,
      "manual_start_date":      "2026-05-18",
      "dependencies":           [],
      "parent_id":              null,
      "is_complete":            false,
      "actual_completion_date": null,
      "delay_days":             0,
      "delay_log":              []
    }
  ]
}
```

## Validation summary

For the full list of validators and the error types they raise, see [API.md §validate_project](API.md#validate_projectproject---liststr).

Tier 1 (structural — fails fast at load): schema-level violations, malformed JSON, missing required fields.

Tier 2 (logical — collects all errors): duplicate IDs, missing/circular/self-dependencies, invalid parent relationships, unanchored leaves, parents with cycle time, completion / location / delay value sanity.

## Per-task examples

### Leaf with manual start, no dependencies

```jsonc
{
  "id":                     "TASK-001",
  "name":                   "Program kickoff",
  "completion_location":    "DAL",
  "calendar_mode":          "working_days",
  "cycle_time_days":        1,
  "manual_start_date":      "2026-05-18",
  "dependencies":           [],
  "parent_id":              null,
  "is_complete":            false,
  "actual_completion_date": null,
  "delay_days":             0,
  "delay_log":              []
}
```

### Leaf with a dependency, no manual start (anchored via dependency)

```jsonc
{
  "id":                     "TASK-002",
  "name":                   "Wafer fab",
  "completion_location":    "TAI",
  "calendar_mode":          "e_days",
  "cycle_time_days":        21,
  "manual_start_date":      null,
  "dependencies":           [ { "id": "TASK-001", "type": "FS", "lag_days": 0 } ],
  "parent_id":              null,
  "is_complete":            false,
  "actual_completion_date": null,
  "delay_days":             0,
  "delay_log":              []
}
```

### Parent task (no cycle_time, no manual_start; derives from children)

```jsonc
{
  "id":                     "TASK-010",
  "name":                   "Burn-in stage",
  "completion_location":    "AIZU",
  "calendar_mode":          "e_days",
  "cycle_time_days":        null,
  "manual_start_date":      null,
  "dependencies":           [],
  "parent_id":              null,
  "is_complete":            false,
  "actual_completion_date": null,
  "delay_days":             0,
  "delay_log":              []
}
```

### Subtask (child of TASK-010)

```jsonc
{
  "id":                     "TASK-011",
  "name":                   "Stage 1 bake",
  "completion_location":    "AIZU",
  "calendar_mode":          "e_days",
  "cycle_time_days":        7,
  "manual_start_date":      null,
  "dependencies":           [ { "id": "TASK-009", "type": "FS", "lag_days": 0 } ],
  "parent_id":              "TASK-010",
  "is_complete":            false,
  "actual_completion_date": null,
  "delay_days":             0,
  "delay_log":              []
}
```

### Completed task

```jsonc
{
  "id":                     "TASK-005",
  "name":                   "Order parts",
  "completion_location":    "DAL",
  "calendar_mode":          "e_days",
  "cycle_time_days":        2,
  "manual_start_date":      null,
  "dependencies":           [ { "id": "TASK-001", "type": "FS", "lag_days": 0 } ],
  "parent_id":              null,
  "is_complete":            true,
  "actual_completion_date": "2026-05-22",
  "delay_days":             1,
  "delay_log":              [
    {
      "date":       "2026-05-21",
      "source":     "auto",
      "days_added": 1,
      "reason":     "auto-catchup since 2026-05-19"
    }
  ]
}
```

Notice: even though `delay_days` is 1, the `effective_finish` for dependent tasks uses `actual_completion_date` (2026-05-22), not `computed_finish + 1`. Completion freezes the effective date.
