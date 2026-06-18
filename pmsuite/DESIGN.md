# DESIGN — PMSuite Gantt Builder

This document records the design decisions behind PMSuite. It is the durable companion to the JSON source of truth and the Python code. When code disagrees with this document, fix one of them — they should always be in sync.

## 1. Purpose

A Python tool that generates Excel Gantt chart workbooks from a structured JSON project file. Designed for **semiconductor New Product Development & Execution (NPDE) workflows** that span multiple global sites with different work-weeks and holidays.

### Pipeline

```
JSON project file (source of truth)
    →  Loader / Validator
    →  Scheduling engine
    →  Excel builder (xlsxwriter)
    →  Timestamped .xlsx in output/
```

The Streamlit UI is a thin client over the documented Python API. Manual edits to the generated Excel workbook **do not** sync back to JSON.

## 2. Non-goals (v1)

- GUI dashboard beyond local Streamlit
- Cloud hosting or multi-user collaboration
- Cross-project dependencies
- Syncing manual Excel edits back into JSON
- Complex resource leveling or cost tracking
- Microsoft Project format compatibility
- Custom corporate calendar logic

## 3. Architecture

- **Pure Python module**, no HTTP service. The Streamlit UI imports the API directly.
- **Pydantic v2 models** are the canonical in-memory representation. They serialize losslessly to JSON.
- **Stateful `Project` object** held in `st.session_state` during a Streamlit session; **stateless module functions** for I/O (`load_project`, `save_project`, `build_excel`).
- **Structured `GanttError` exception hierarchy** with `.to_envelope()` for serialization across the UI boundary.

## 4. Data model

### 4.1 Top-level project file

```jsonc
{
  "project": { "id", "name", "timezone", "created_at", "updated_at",
               "last_export": null | { "path", "at" },
               "history": [ ... ] },
  "settings": { "holidays", "work_weeks", "next_task_id", "output_directory",
                "keep_local_snapshots", "auto_delay_on_load",
                "last_auto_delay_run", "date_axis_start", "date_axis_end" },
  "tasks":    [ ... ]
}
```

### 4.2 Task

```jsonc
{
  "id":                    "TASK-001",                  // system-generated
  "name":                  "Wafer fab",                 // user-provided
  "completion_location":   "TAI",                       // required, 1 of 8 enum
  "calendar_mode":         "e_days" | "working_days",   // required
  "cycle_time_days":       21,                          // required when leaf
  "manual_start_date":     "2026-05-18" | null,         // floor; required when leaf with no deps
  "dependencies":          [ { "id", "type", "lag_days" } ],
  "parent_id":             null | "TASK-XXX",
  "is_complete":           false,
  "actual_completion_date": null | "2026-05-18",
  "delay_days":            0,
  "delay_log":             [ { "date", "source", "days_added", "reason?" } ]
}
```

### 4.3 Derived fields (NOT stored in JSON)

`has_subtasks`, `computed_start`, `computed_finish`, `effective_finish`, `total_float`, `is_critical`, `is_overdue`, `hierarchy_level`. Re-derived per schedule run.

### 4.4 Canonical serialization

Pydantic emits with `model_dump(mode="json", exclude_defaults=False, exclude_none=False)`. Every field present in every task with explicit defaults — predictable diffs in git, readable JSON.

## 5. Task identifiers

System-generated sequential `TASK-NNN` (zero-padded to ≥3 digits). User provides task names only.

Gaps allowed; IDs never reuse. The project tracks `settings.next_task_id` for O(1) generation. Subtask IDs share the flat numbering pool (hierarchy is via `parent_id`, not via ID structure).

## 6. Locations

V1 closed enum, 8 locations:

| Code   | Place                       | Work-week (USA-perspective) | Holiday seed (Python `holidays`) |
|--------|-----------------------------|-----------------------------|----------------------------------|
| DAL    | Dallas, USA                 | Mon–Fri                     | `holidays.US()`                  |
| FR-BIP | Freising, Germany           | Mon–Fri                     | `holidays.Germany(subdiv="BY")`  |
| MLA    | Kuala Lumpur, Malaysia      | Sun–Thu                     | `holidays.Malaysia(subdiv="KUL")`|
| TIEMA  | Melaka, Malaysia            | Sun–Thu                     | `holidays.Malaysia(subdiv="MLK")`|
| CLARK  | Clark, Philippines          | Sun–Thu                     | `holidays.Philippines()`         |
| TIPI   | Baguio, Philippines         | Sun–Thu                     | `holidays.Philippines()`         |
| TAI    | Taiwan                      | Sun–Thu                     | `holidays.Taiwan()`              |
| AIZU   | Aizu, Japan                 | Sun–Thu                     | `holidays.Japan()`               |

### USA-perspective work-week rule

At 10 AM Chicago Friday, check local time at the site. If local time is ≥ 11 PM Friday (i.e., the site has finished its Friday before the USA Friday workday begins), the work-week is modeled as **Sun–Thu** from USA-perspective. Otherwise Mon–Fri.

This produces clean scheduling alignment for global handoffs: the USA team sees their Monday morning as "what finished overseas over the weekend." A Malaysian fab that closes Friday at 6 PM local time has effectively finished USA's Thursday.

### Holiday model

- **Object form** in JSON: `[{date, name, source: "seeded"|"user-added"|"user-edited"}]`.
- **Partitioned by location**: `settings.holidays.DAL`, `settings.holidays.MLA`, etc.
- **Local-date storage** (no USA-perspective shift on dates). The 1-day timezone slop is smaller than the system's day-resolution granularity.
- **Seeded from `holidays` library** at project creation / first encounter of a location. After seeding, JSON is canonical; library is never consulted again unless the user clicks "Re-seed from library" (which surfaces a diff before applying).
- E-day tasks honor location holidays (ovens may run continuously but sites observe national holidays).
- V1 enum is closed; more countries to be added in V2.

## 7. Scheduling rules

### 7.1 Cycle time

**Inclusive.** `cycle_time_days: 5` starting Friday (e-day) finishes Tuesday. `cycle_time_days: 0` is a validation error. A successor task starts the **day after** the predecessor's finish (FS, 0 lag).

### 7.2 Calendar modes

- `e_days`: cycle time counts every calendar day. Used for processes like oven cycles that run continuously.
- `working_days`: cycle time counts only the location's working-week days minus holidays. Used for human-bound processes like documentation, design review, qualification reports.

### 7.3 Cross-mode dependency boundaries

**Successor's calendar mode governs.** A working-day successor snaps forward to the next working day in its own calendar before counting. An e-day successor starts the next calendar day regardless of the predecessor's calendar mode.

### 7.4 Manual start as floor

`effective_start = max(manual_start_date or -inf, latest_predecessor_finish_with_lag, parent_effective_floor if any)`.

Tasks with **neither** a manual start nor a dependency are unanchored — validation error.

### 7.5 Day resolution only

No hours. Times in `created_at` / `updated_at` are audit-only metadata; scheduling math is at day granularity.

## 8. Dependencies

Rich relationship types with lag:

| Type | Meaning                                                |
|------|--------------------------------------------------------|
| FS   | Finish-to-Start (default). Successor starts after predecessor finishes. |
| SS   | Start-to-Start. Successor starts when predecessor starts. |
| FF   | Finish-to-Finish. Successor finishes when predecessor finishes. |
| SF   | Start-to-Finish. Successor finishes when predecessor starts. |

`lag_days`: positive = delay, negative = lead. Counted in **predecessor's** calendar mode. After lag is applied, the successor's start is then resolved per its own calendar mode.

Bare-string shorthand:
```json
"dependencies": ["TASK-001"]
```
…is equivalent to `[{"id":"TASK-001","type":"FS","lag_days":0}]`. The Streamlit UI accepts both; serialization normalizes to the object form.

The Streamlit UI must include a **"Dependency Explanation" expander** explaining FS/SS/FF/SF in plain language.

FS / SS / FF / SF are implemented. `lag_days` is counted in the predecessor's calendar mode; after lag is applied, the successor resolves in its own calendar mode.

## 9. Parent / subtask hierarchy

- Multi-level tree, unlimited depth.
- Parents identified by having children (other tasks with `parent_id == this.id`). `has_subtasks` is **derived, not stored**.
- Parents may have their own dependencies and their own `manual_start_date` (acts as floor for ALL descendants).
- Parent's `cycle_time_days` must be unset (validation error if set). Parent duration is derived: `parent_end - parent_start + 1` (inclusive calendar span).
- Parent start/end are rolled up from children: `start = earliest_child_start`, `end = latest_child_end`.

## 10. Completion semantics

- `is_complete: true` requires `actual_completion_date` to be present. The Streamlit UI auto-fills today's date when the checkbox flips on, but the value is persisted in JSON.
- **Early completion allowed.** A task can be completed before its scheduled start. The Gantt is a living document, not a frozen plan.
- **Completion freezes effective dates.** Dependents key off `actual_completion_date`, not the previously computed finish.
- **Parent completion cascades to all descendants** — every leaf gets `is_complete: true` and `actual_completion_date = parent's actual_completion_date`, regardless of cycle times. Children with their own earlier `actual_completion_date` retain their earlier date (don't destroy real history).
- **Unset is supported.** Toggling `is_complete: true → false` clears `actual_completion_date` and returns the task to dependency-driven scheduling.

## 11. Delays

### 11.1 `delay_days` is cumulative

Stored in JSON. Both manual user input and the daily auto-check add to it. Scheduler: `finish = computed_finish + delay_days` (in the task's calendar mode).

### 11.2 Auto-applied on project load

Idempotent by `settings.last_auto_delay_run` (date). When the user opens a project after N missed days, the system computes how many days each overdue task was overdue and applies the catch-up.

**Multi-day catch-up math: Option B (per-task accurate, static).** For each overdue task, add `max(0, today - effective_finish)`. Logged as a single `delay_log` entry: `source: "auto"`, reason `"auto-catchup since YYYY-MM-DD"`. Upstream delays do NOT inflate downstream `delay_days` — downstream shifts via the dependency cascade only.

### 11.3 UI flow

The auto-catchup is **prompted on load** ("Apply / Skip / Settings"), not silent. After application, a dismissible banner reports what changed; an expander shows per-task detail; affected rows are tinted until next save. **One-click undo within the session** reverts the batch atomically; manual edits to affected tasks block their individual undo with a notice.

Manual "Apply Daily Delays Now" button always available. No cron — projects drive themselves when opened. `settings.auto_delay_on_load: true` by default; users may disable per project.

### 11.4 Completion freezes delay_days

Once `is_complete: true`, `delay_days` is preserved historically but no longer applied (since `actual_completion_date` is now truth). Excel can show "Accumulated delay: 3 days; Actual finish: on time."

## 12. Critical path

- **Total float:** computed with a CPM-style backward pass.
- **Displayed critical path:** the user-visible red-bar critical set is the long pole: terminal unfinished leaves and the transitive chain of gating predecessors that drive the project end. This avoids working-day boundary snapping making the obvious gating chain appear non-critical due to small artificial float.
- Project end derived from latest leaf `effective_finish`. No user-specified target end date.
- **Total float only** in v1; free float skipped.
- Forward + backward pass per CPM standard. Lag included in path duration.
- Critical/float values derived per schedule run; NOT stored in JSON.
- Completed tasks excluded from live critical path. `was_on_critical_path` is snapshotted into `project.history` at completion time for the audit column on Schedule Calculations.
- All tied critical paths are marked.

Current implementation computes total float for diagnostics and uses the long-pole critical set for Excel critical-path highlighting.

## 13. Validation

**Two-tier collect:**
- Tier 1 (structural — malformed JSON, missing required fields): handled at load time, fails fast.
- Tier 2 (logical — circular deps, duplicate IDs, invalid dates, parent-cycle-time conflicts, unanchored tasks, missing dependency references, etc.): collected into `ValidationFailure(errors=[...])` and raised together.

**Save behavior:** writes always succeed if structurally valid; logical errors are surfaced inline but don't block save. **Build Excel** is gated on clean logical validation.

**Warnings** are collected separately, never block.

## 14. Excel output

### 14.1 Library

`xlsxwriter` for production (regenerate-only model fits its write-only constraint). `openpyxl` for tests (loading generated files for structural assertions).

### 14.2 Output filename

```
output/gantt_<project_id>_<YYYY-MM-DD>_<HHMMSS>.xlsx
```

- Timestamp in project timezone (default `America/Chicago`).
- Lexically sortable; most recent always at the bottom of an alphabetical sort.
- No `_latest.xlsx` auto-copy — avoids the "which file is current?" question.
- Collision-safe via `_2`, `_3` suffix if multiple builds fire in the same second.
- No automatic retention or cleanup in v1.

### 14.3 Workbook sheets

1. **Chart Key & Info** — legend, working-week reference, and frozen-pane guide.
2. **Day View** — one column per day across full axis (scrollable).
3. **Week View** — one column per week across same axis.
4. **Schedule Calculations** — full audit table.
5. **Critical Path Notes** — summary + dashboards.

Frozen panes: task metadata columns frozen left, date header row frozen top. The full date range is rendered (no compression); user scrolls horizontally.

### 14.3.1 Gantt row order

Day View and Week View display tasks in chronological schedule order, not ID order or JSON insertion order. Task IDs are stable creation identifiers and are never renumbered for display. For example, a later-created `TASK-013` appears between `TASK-009` and `TASK-010` when its computed schedule dates fall between those tasks.

### 14.4 Bar rendering (Option E — segmented cell coloring)

- **Planned** (incomplete): pale blue (`#8FB6E1`).
- **Completed**: green (`#2E8B57`).
- **Delay extension**: orange (`#E68A00`).
- **Overdue**: red (`#D9534F`) fill or outline.
- **Critical path indicator**: dark red border / left stripe (`#8B0000`).
- **Today column**: pale yellow (`#FFF8C4`).
- **Weekend**: light gray (`#F0F0F0`).
- **Holiday**: darker gray (`#B0B0B0`), holiday name in column header.
- **Parent summary bar**: dark gray with black border caps (`#555555`).

No text on bars (would conflict with short bars at day resolution). Task ID + name live in the frozen leftmost columns.

### 14.5 Axis derivation

```
start_axis = floor_to_monday(min(earliest_task_start, today) - 7 days)
end_axis   = ceil_to_sunday (max(latest_effective_finish, today) + 14 days)
```

Today always included. Monday week start (USA-anchored ISO 8601). Override via `settings.date_axis_start` / `date_axis_end`.

### 14.6 Schedule Calculations columns (left to right)

`TASK ID | Name | Hierarchy Level | Parent ID | Location | Calendar Mode | Cycle Time | Manual Start Date | Computed Start | Computed Finish | Delay Days | Effective Finish | Actual Completion Date | Is Complete | Dependencies | Total Float | Is Critical | Was On Critical Path | Downstream Impact | Validation Warnings`

### 14.7 Critical Path Notes layout

1. Summary block: project name, derived end date, total duration, counts.
2. Critical path tasks (table).
3. Tasks currently delaying the project.
4. Top 5 near-critical tasks (lowest non-zero float).
5. Overdue incomplete tasks.
6. Recently completed late.
7. Recently completed early.
8. Dependency warnings.
9. Auto-generated plain-language summary at the top.

## 15. API contract

```python
from gantt_builder import api

project = api.load_project(path)              # -> Project | raises StructuralError
warnings = api.validate_project(project)      # -> list[str] | raises ValidationFailure
schedule = api.schedule_project(project)      # -> dict[task_id -> ScheduledTask]
output_path = api.build_excel(project)        # -> Path | raises ValidationFailure
api.save_project(project, path)               # atomic write
```

Errors are pythonic exceptions. The Streamlit UI catches `GanttError` subclasses and renders `.to_envelope()` for display.

## 16. File / directory layout

```
PMsuite/
├── .github/workflows/test.yml
├── .gitignore                       # projects/, output/, .logs/, .streamlit/recents.json all ignored
├── README.md
├── DESIGN.md                        # this file
├── pyproject.toml
├── gantt_builder/                   # the Python package
│   ├── api.py
│   ├── errors.py
│   ├── models.py
│   ├── locations.py
│   ├── logging_config.py
│   ├── project_io.py
│   ├── validation.py
│   ├── scheduler.py
│   ├── critical_path.py
│   └── excel_builder.py
├── ui/streamlit_app.py              # local-only Streamlit UI
├── tests/
├── examples/
│   ├── small_demo.json              # 7 tasks, DAL only — dual-purpose example + fixture
│   └── npde_demo.json               # multi-location demo (starter; will grow)
├── projects/                        # GITIGNORED — your project JSONs (per-user)
│   └── .backups/                    # rotating snapshots
├── output/                          # GITIGNORED except .gitkeep — generated Excel
└── .logs/gantt_builder.log          # GITIGNORED — rotating log file (always on)
```

### Data locality

**User project JSON files live LOCALLY on each user's machine** in `projects/`. They are NEVER pushed to GitHub. The GitHub repo holds source code, docs, and example projects only. Users back up `projects/` themselves (cloud / network share / external drive). Local rotating snapshots in `projects/.backups/` provide crash recovery.

## 17. Streamlit UX

- **File picker:** sidebar dropdown of `projects/*.json` + `examples/*.json`. Optional "Open from path…" for external paths.
- **New Project button:** form for name, ID (auto-slugged, editable), timezone, default calendar mode, output directory. Writes skeleton to `projects/{slug}.json`.
- **Save:** explicit button with dirty-state badge. Browser `beforeunload` warning when dirty. No auto-save.
- **Single project per session.** Switching with unsaved changes triggers Cancel / Discard / Save & Switch dialog.
- **Validating spinners** during long operations.
- **Holiday editor page:** tabbed view (one tab per location), table of `{date, name, source}`, add/edit/delete, "Re-seed from library" with diff preview.
- **Auto-catchup banner** after applying delays on load — dismissible, expandable detail, one-click undo.

## 18. Testing strategy

`pytest -q` runs the fast suite. Performance tests are marked `slow` and run separately.

Test files cover behavior contracts (not internal implementation details):

```
tests/test_models.py            # pydantic validation, dependency shorthand
tests/test_project_io.py        # load/save round-trip, canonical writes, timezone audit fields
tests/test_api.py               # end-to-end pipeline (load → validate → schedule → build)
tests/test_validation.py        # parent-cycle and parent/dependency safety
tests/test_scheduler.py         # (TODO) calendar math, FS/SS/FF/SF
tests/test_delays.py            # cumulative delay, catch-up, max-cascade, undo
tests/test_completion.py        # freeze, parent cascade, unset, undo
tests/test_dependencies.py      # lag, FS/SS/FF/SF, parent-aware scheduling
tests/test_critical_path.py     # CPM float, long-pole critical set, parent inheritance
tests/test_locations.py         # (TODO) work-week + holiday per location
tests/test_holidays.py          # (TODO) editor logic, re-seed diff
tests/test_excel_builder.py     # structural formatting assertions
tests/test_editing.py           # Step 6 add/update/delete/dependency API primitives
tests/test_excel_visual.py      # (TODO, opt-in) visual rendering
tests/test_performance.py       # (TODO, slow) 300 / 1000 / 2000 tasks
```

Walking-skeleton ships the first three; the rest are filled in as features are implemented.

**Excel testing:** hybrid (structural assertions via openpyxl + opt-in visual snapshots). No binary diffs.

## 19. Performance budget

Cold start at typical project size (~50–300 tasks): **< 6 seconds total** (load → validate → schedule → build Excel).

No task ceiling. 2000-task projects work; they just take longer. Optimization target is the 50–300 sweet spot; design choices favor readability and reliability over performance contortions.

## 20. Logging

Always on. Rotating file handler at `.logs/gantt_builder.log` (10 MB, last 5 retained) + stderr stream. Default level `INFO`. Setup is idempotent via `logging_config.configure_logging()`; modules use `get_logger(__name__)`.

## 21. Current Step 5 state — what works today

- Load / validate / save JSON project files.
- Forward-pass scheduling with FS / SS / FF / SF dependencies, predecessor-calendar lag, manual-start floors, parent-inherited floors/dependencies, e-day + working-day calendar math, holiday awareness, and parent rollup.
- Atomic JSON writes with optional rotating snapshots.
- Excel workbook generation with all 5 sheets, full Option E Gantt cell coloring, frozen panes, baseline columns, dependency column, today line, holiday/weekend gaps, parent summary bars, and chart key.
- Streamlit shell: pick project, view tasks, validate, save, build Excel.
- `pytest -q` covers model validation, JSON I/O round-tripping, end-to-end pipeline.

## 22. What's still pending after Step 5

- Streamlit task editing (add / edit / delete / dependency picker / holiday editor).
- Dirty-state badge + browser `beforeunload` warning.
- New Project button workflow.
- Holiday seeding UI and re-seed diff.
- Expanded NPDE demo with 30-50 public-domain tasks.
- Broader test backfill for locations, holiday editor logic, visual Excel snapshots, and performance.

## Decision log

The grilling session that produced this design walked 26 numbered questions and their resolutions. They are referenced inline throughout this document where relevant. The conversation transcript is in the prior grilling session; the resolution of each question is captured in the corresponding section above.
