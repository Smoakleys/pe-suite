# MASTERECAP — Every Design Decision

This document enumerates every design decision made during the grilling session that produced PMSuite Gantt Builder. Each decision is anchored to its question number (Q1-Q26 in chronological grilling order) so future debates can reference an exact source.

For architecture-level rationale, see [DESIGN.md](DESIGN.md). For schema details, [JSONFILE.md](JSONFILE.md). For API contract, [API.md](API.md). For Excel output, [EXCELBUILDER.md](EXCELBUILDER.md). For UI spec, [STREAMLIT.md](STREAMLIT.md).

---

## Q1 — Calendar mode (e-day vs working-day)

**Decision:** Per-task. Each task has `calendar_mode: "e_days" | "working_days"`. NPDE rationale: oven cycles (e-days) and reporting (working days) coexist within a single project.

**Why:** Mixing per-project would force the user to artificially split workflows; mixing per-task is the natural unit.

---

## Q2 — Calendar mode granularity

**Decision:** Per-task setting, not per-project.

**Why:** Same project routinely contains both oven-cycle tasks (continuous) and reporting tasks (business days). Per-project would lose this fidelity.

---

## Q3 — Cross-mode dependency boundary

**Decision:** **Successor's calendar mode governs.** A working-day successor of an e-day predecessor snaps to the next working day; an e-day successor of a working-day predecessor starts the next calendar day.

**Why:** The successor's calendar mode is what defines "when can this task actually start?" The predecessor's mode is irrelevant once the predecessor is done.

---

## Q4 — Time resolution

**Decision:** Day resolution only. **No hours.**

- Drop `task_start_time` and `day_end_time` from settings.
- `actual_completion_datetime` → `actual_completion_date`.
- `created_at` / `updated_at` may remain ISO timestamps for audit metadata only; scheduling math is at day granularity.

**Why:** Simplification cuts the data model significantly without losing user value. Auto-daily-delay checks become "once per day" rather than time-windowed.

---

## Q5 — Cycle time interpretation

**Decision:** **Inclusive cycle times.** `cycle_time_days: 5` starting Friday (e-day) finishes Tuesday. A 1-day task starts and finishes on the same day. Successor starts the day AFTER predecessor's finish (FS, 0 lag).

`cycle_time_days: 0` is a validation error. Minimum 1.

**Why:** Matches human intuition ("this takes 5 days" = 5-day-wide bar on the Gantt). Inclusive is the natural reading.

---

## Q6 — `manual_start_date` semantics

**Decision:** Acts as a **floor**, max-combined with dependency-driven starts and parent floor.

```
effective_start = max(
    manual_start_date or -inf,
    latest_predecessor_finish + 1 (per dep type / lag),
    parent_effective_floor (if any)
)
```

A leaf task with **neither** a manual start nor a dependency is a validation error (unanchored).

**Why:** Most expressive option. Users can express "no earlier than 2026-06-01 AND after parts arrive" naturally.

---

## Q7 — Parent / subtask hierarchy

**Decisions:**

- **7a — Multi-level tree, unlimited depth.** Subtasks can have their own subtasks.
- **7b — Parents may have their own dependencies.** Treated like leaves for scheduling-floor purposes.
- **7c — Parents may have their own `manual_start_date`** which acts as a floor for ALL descendant children.
- **7d — Parent duration = `parent_end - parent_start + 1`** (inclusive calendar span). Parent's `cycle_time_days` MUST be unset (validation error if present).

Parent start/end is rolled up from descendants: `start = earliest_child_start`, `end = latest_child_end`.

**Why:** NPDE projects naturally nest. Restricting parents from having their own scheduling state would force awkward workarounds.

---

## Q8 — Completion semantics

**Decisions:**

- **8a — `actual_completion_date` auto-fills today** when the user checks `is_complete`. UI must make it impossible to mark complete without a date. Validation enforces.
- **8b — Early completion allowed.** A task can be completed before its scheduled start.
- **8c — Completion freezes effective dates.** Dependents key off `actual_completion_date`, not the previously computed finish.
- **8d — Parent completion cascades to all descendants.** Every descendant leaf gets `is_complete: true` and `actual_completion_date = parent's actual_completion_date`. **However: children with their own *earlier* `actual_completion_date` retain their earlier date** (don't destroy real history). User confirmed common-sense reading on resume.
- **8e — Unset supported.** `is_complete: true → false` clears `actual_completion_date` and returns task to dependency-driven scheduling.

**Why:** "Living document" philosophy — the user's reality drives the schedule, and the schedule must adapt to early/late completion without forcing the user to manually fix dependents.

---

## Q9 — Delay mechanics

**Decisions:**

- **9a — `delay_days` cumulative**, stored in JSON. Both manual user input and auto-daily checks add to it. Scheduler: `effective_finish = computed_finish + delay_days` (in task's calendar mode).
- **9b — Auto-applied on project load**, idempotent by `settings.last_auto_delay_run` (date). Plus manual "Apply Daily Delays Now" button. No cron (work laptops can't reliably run it).
- **9c — Completion freezes `delay_days`** as historical record (preserved; no longer applied because `actual_completion_date` is now truth).
- **9d — Single `delay_days` field + `delay_log` array** of `{date, source: "manual"|"auto", days_added, reason?}`. Scheduler reads sum; UI/Excel read log.
- **9e — Spec rule #8 (max-cascade-once)** holds within one recalculation pass. **Upstream delay does NOT inflate downstream `delay_days`** — downstream shifts via dependency cascade only.

**Why:** Delays are first-class state, not derived. The audit trail (`delay_log`) is what makes the system trustworthy when delays accumulate over time.

---

## Q10 — Task IDs

**Decisions:**

- **10a — System-generated**, opaque format. User provides task **name** only.
- **10b — Sequential `TASK-NNN`**, zero-padded to ≥3 digits.
- **10c — Gaps allowed**, IDs never reused. `settings.next_task_id` tracks the counter for O(1) generation.
- **10d — Streamlit shows both** TASK ID and Name in the table. Dependency picker shows `TASK-003 — Order bHAST boards`.

Subtask IDs share the flat numbering pool; hierarchy is via `parent_id`, not via ID structure.

**Why:** Stable IDs survive renaming. System generation eliminates duplicate-ID validation surface.

---

## Q11 — Multi-day auto-catchup math

**Decision:** **Option B (per-task accurate, static).** For each currently-overdue task, add `max(0, today - effective_finish)` to its `delay_days`. Logged as a single `delay_log` entry: `source: "auto"`, reason `"auto-catchup since YYYY-MM-DD"`.

Does NOT replay the daily cascade (Option C); does NOT lump-sum to all overdue tasks regardless of when they became overdue (Option A).

**Why:** Per-task accurate. Cheap to compute. Matches the "upstream delays don't inflate downstream delay_days" rule.

---

## Q12 — API architecture

**Decisions:**

- **12a — Pure Python module.** No HTTP service. Streamlit imports directly.
- **12b — Stateful `Project` object** in `st.session_state`; **stateless module functions** for I/O.
- **12c — Pydantic v2 models** for `Project` / `Task` / `Dependency` / `Settings`.
- **12d — Custom exception hierarchy** with `GanttError.to_envelope()`. Pythonic in-process; Streamlit catches at the UI boundary.

**Why:** Work laptops can't reliably run extra services. A pure Python module is simpler, faster to test, easier to swap a CLI/HTTP layer over later.

---

## Q13 — Validation strategy

**Decision:** **Two-tier collect.**

- Tier 1 (structural — malformed JSON, missing required fields): handled at load time. Fails fast.
- Tier 2 (logical — circular deps, duplicate IDs, invalid dates, etc.): collects all errors, raises `ValidationFailure(errors=[GanttError, ...])`.

**Save always writes** if structurally valid; logical errors shown inline but don't block save.

**Build Excel is gated** on clean logical validation.

**Warnings** collected separately, never block.

**Why:** UX win — a 100-task project with five problems shouldn't make the user click "Save → fix → Save" five times.

---

## Q14 — Excel library

**Decision:** **`xlsxwriter` for production, `openpyxl` for tests.**

- Production builds are write-only (regenerate-from-JSON model fits xlsxwriter perfectly).
- Tests load generated files via `openpyxl` for structural assertions.
- xlsxwriter's outline grouping, conditional formatting, and scale-friendly write performance beat openpyxl for our regenerate workflow.

**Why:** Regenerate-only model means we never need to read/modify existing workbooks in production; xlsxwriter's read limitation costs us nothing.

---

## Q15 — Gantt bar rendering

**Decision:** **Option E — segmented static cell coloring.**

- Planned: pale blue `#8FB6E1` (checkpoint-2 readability update).
- Completed: green `#2E8B57`.
- Delay extension (computed_finish → effective_finish): orange `#E68A00`.
- Overdue (today > effective_finish, incomplete): red `#D9534F` outline/fill.
- Critical path indicator: dark red `#8B0000` border or left stripe.
- Today column: pale yellow `#FFF8C4`.
- Weekend column (day view): light gray `#F0F0F0`.
- Holiday column (day view, location-specific): darker gray `#B0B0B0` + name in column header.
- Parent summary bar: dark gray `#555555` with black border caps; not body-filled.

**No text on bars.** Task ID + name live in frozen leftmost columns.

**Why:** Static cell colors scale; merged cells break outline grouping; native charts can't combine with row grouping; segmented colors carry all required status encoding.

---

## Q16 — Output filename and retention

**Decisions:**

- Filename: `gantt_<project_id>_<YYYY-MM-DD>_<HHMMSS>.xlsx`.
- Path: `<output_dir>/<filename>`, default `output/`, configurable via `settings.output_directory`.
- Timestamp in project timezone (default `America/Chicago`).
- **No `_latest.xlsx` auto-copy.** Lexically sortable filenames mean "most recent" is unambiguous.
- Collision-safe: `_2`, `_3` suffix if same-second collision (rare).
- No automatic retention/cleanup in v1.
- JSON tracks `project.last_export: {path, at}` after each build.

**Why:** Versioned history with zero ambiguity about which file is current.

---

## Q17 — Critical path

**Decisions:**

- **CPM-style:** critical = `total_float == 0`.
- **Project end:** derived from latest leaf `effective_finish`. No user-specified target.
- **Total float only** in v1; free float skipped (revisit if users ask).
- **Completed tasks excluded** from live critical path. `was_on_critical_path` snapshotted into `project.history` at completion for audit.
- **All tied critical paths marked** (no canonical pick).
- **Lag included** in path duration (positive lengthens, negative shortens).

Critical / float values are **derived, never stored** in JSON.

**Why:** CPM is the textbook definition project managers expect. Snapshotting at completion preserves history without sync drift.

---

## Q18 — Workbook date axis

**Decision:** **Padded + Monday-aligned**, automatic with override.

```
start_axis = floor_to_monday(min(earliest_task_start, today) - 7 days)
end_axis   = ceil_to_sunday (max(latest_effective_finish, today) + 14 days)
```

- Today always in axis.
- Day View = 1 column per day; Week View = 1 column per week; SAME span policy.
- Monday week start in v1 (ISO 8601, USA-anchored).
- Override via `settings.date_axis_start` / `settings.date_axis_end`.

**Why:** Users always see "today" in context. Monday week-start matches MS Project / Primavera / Jira norms.

---

## Q19 — Per-task location

**Decisions:**

- **`completion_location` is REQUIRED on every task.** No project-level default.
- **8-location closed enum** for v1 (DAL, FR-BIP, MLA, TIEMA, CLARK, TIPI, TAI, AIZU). V2 may add more.
- **E-day tasks honor location holidays** but ignore work-week.
- **Holidays partitioned by location** in `settings.holidays.<LOCATION>`.
- **Week View column headers** labeled by Monday-of-week in USA dates. Task location shown as a metadata column. **Single Week View sheet** — no per-location duplicate sheets.
- **Holiday editor UI required** for v1 (user must be able to add/edit/remove holidays per location).

**Why:** Per-task location enables multi-site programs (typical NPDE). Team is USA-based but tasks fan out globally.

---

## Q20 — Location specifics and the USA-perspective work-week rule

**Decisions:**

**USA-perspective work-week rule:** At 10 AM Chicago Friday, check local time at each site. If local time is ≥ 11 PM Friday (i.e., the site has finished its Friday before USA arrives at office), shift the work-week to **Sun–Thu** from USA-perspective. Otherwise **Mon–Fri**.

Equivalent: sites at **UTC+8 or later** are Sun–Thu in USA-perspective.

Applied to all 8 locations:

| Location | Place                    | UTC offset | Local time @ 10 AM CDT Fri | USA-perspective work-week |
|----------|--------------------------|------------|----------------------------|---------------------------|
| DAL      | Dallas, USA              | UTC−5      | 10:00 Fri                  | Mon–Fri                   |
| FR-BIP   | Freising, Germany        | UTC+2      | 17:00 Fri                  | Mon–Fri                   |
| MLA      | Kuala Lumpur, Malaysia   | UTC+8      | 23:00 Fri                  | Sun–Thu                   |
| TIEMA    | Melaka, Malaysia         | UTC+8      | 23:00 Fri                  | Sun–Thu                   |
| CLARK    | Clark, Philippines       | UTC+8      | 23:00 Fri                  | Sun–Thu                   |
| TIPI     | Baguio, **Philippines**  | UTC+8      | 23:00 Fri                  | Sun–Thu                   |
| TAI      | Taiwan                   | UTC+8      | 23:00 Fri                  | Sun–Thu                   |
| AIZU     | Aizu, Japan              | UTC+9      | 00:00 Sat                  | Sun–Thu                   |

**TIPI correction:** initially listed as Taiwan, user corrected to Baguio, Philippines. `LOCATION_TO_LIBRARY` accordingly: CLARK and TIPI both seed from `holidays.Philippines()` but get separate editable buckets.

**Library seed mapping (in code):**

```python
LOCATION_TO_LIBRARY = {
    "DAL":    holidays.US(),
    "FR-BIP": holidays.Germany(subdiv="BY"),       # Bavaria (Freising in Upper Bavaria)
    "MLA":    holidays.Malaysia(subdiv="KUL"),     # Kuala Lumpur
    "TIEMA":  holidays.Malaysia(subdiv="MLK"),     # Melaka
    "CLARK":  holidays.Philippines(),
    "TIPI":   holidays.Philippines(),              # Baguio (corrected from Taiwan)
    "TAI":    holidays.Taiwan(),
    "AIZU":   holidays.Japan(),
}
```

**Holiday editor:** dedicated Streamlit page, tabbed by location, table of `{date, name, source}`. "Re-seed from library" button shows a diff vs. current (no silent overwrites).

---

## Q21 — Holiday date storage

**Decision:** **Local-date storage, no USA-perspective shift on dates.**

Holiday seed (e.g., `holidays.Taiwan()` returning Feb 10 for Lunar New Year) is stored as-is in JSON: `"date": "2026-02-10"`. No transformation.

**Why:** The 1-day timezone slop is smaller than day-resolution granularity. Matches what users would Google. Aligns with what the library returns. Maximal readability.

---

## Q22 — Schema cleanup

**Decisions:**

- **22a — `has_subtasks` derived, never stored.** Drop from JSON. Computed from `parent_id` references at runtime.
- **22b — Other derived fields not stored:** `computed_start`, `computed_finish`, `effective_finish`, `total_float`, `is_critical`, `is_overdue`, `hierarchy_level`.
- **22c — Stored:** source data + audit trails + idempotency keys. `was_on_critical_path` lives in `project.history` (snapshot at completion).
- **22d — Canonical serialization includes all fields** with explicit defaults. `pydantic.model_dump(exclude_defaults=False, exclude_none=False)`. Predictable git diffs.

**Why:** Eliminates a whole class of sync bugs. Cleaner JSON. Easier to reason about.

---

## Q23 — Git safety and backup

**Decisions:**

- **23a — Atomic JSON writes** via temp file + `os.replace`. Non-negotiable basic hygiene.
- **23b — Local rotating snapshots ON by default.** `settings.keep_local_snapshots: 10` keeps the last 10 in `projects/.backups/<project_id>/`. Set to 0 to disable. Git is NOT the user-data backup mechanism — user projects live LOCALLY.
- **23c/d — `.gitignore`** includes `projects/`, `output/` (except `.gitkeep`), `.logs/`, `.streamlit/recents.json`, Python build/cache, IDE, OS. Only `examples/*.json` ships as committed project data.
- **23e — No pre-commit hooks** in v1; manual `pytest -q` is sufficient.
- **23f — README** uses standard intro + install + quick-start + how-it-works + data-locality callout + cross-refs. License is **MIT**.
- **23g — Two demo projects** ship: `small_demo.json` (7 tasks, DAL only, dual-purpose example + test fixture) and `npde_demo.json` (~30-50 tasks, multi-location — currently 13-task starter awaiting expansion).

**Why:** GitHub repo distributes the source code; users' projects stay on their machines. Local snapshots cover crash recovery; user backs up to their own cloud / network share if they want history beyond that.

---

## Q24 — Auto-delay UI flow

**Decisions:**

- **24a — Option B: prompt before applying.** On load, detect pending catch-up, modal asks Apply / Skip / Settings. User explicitly opts in.
- **24b — After applying: dismissible banner + expandable detail + per-row tint.** Banner reports counts; "View details" expander shows per-task table; affected rows tinted orange until next save.
- **24c — One-click undo of batch** within the session. After save, no undo. Manual edits to a task between auto-apply and undo block that task's individual undo (warning shown).
- **24d — `settings.auto_delay_on_load: true` default.** User can disable per project.
- **24e — Fresh project initialization:** `settings.last_auto_delay_run` set to today on first save without applying any delays. No surprise welcomes.

**Why:** Users see what changes and can revert. Reversibility builds trust.

---

## Q25 — Test strategy and performance

**Decisions:**

- **25a — Test file breakdown:** 12 files split by concern (models, project_io, validation, scheduler, delays, completion, dependencies, critical_path, locations, holidays, api, excel_builder, excel_visual, performance). Walking-skeleton ships first 3; rest filled in alongside feature commits.
- **25b — Hybrid Excel testing:** structural assertions via `openpyxl` (sheet existence, cell values for known tasks, color encoding, frozen pane position, format presence). Visual snapshots are opt-in (`@pytest.mark.visual`). No binary diffs.
- **25c — Performance budget: cold-start < 6 seconds** at typical sizes (50-300 tasks). No task ceiling — 2000+ works, just slower. Optimization target is the 50-300 sweet spot; design favors readability over performance contortions.
- **25d — Fixtures:** small_demo + npde_demo dual-purpose (shipped + tests). Large fixture generated programmatically by `tests/fixtures/large_project_factory.py` for performance tests.
- **25e — GitHub Actions** workflow runs `pytest -q -m "not slow"` on Python 3.11 and 3.12 on every push and PR.

**Test purpose philosophy:** prove behavior contracts, not implementation details. Tests should survive refactors. No 100% coverage chase.

---

## Q26 — Visual specifics and remaining loose ends

**Decisions:**

- **26a — Color palette locked** per the [Q15 table](#q15--gantt-bar-rendering) (planned blue, completed green, delay orange, overdue red, critical dark red border, today yellow, weekend/holiday grays, parent summary dark gray).
- **26b — Schedule Calculations sheet columns** (left to right): `TASK ID | Name | Hierarchy Level | Parent ID | Location | Calendar Mode | Cycle Time | Manual Start Date | Computed Start | Computed Finish | Delay Days | Effective Finish | Actual Completion Date | Is Complete | Dependencies | Total Float | Is Critical | Was On Critical Path | Downstream Impact | Validation Warnings`. Header row frozen; ID and Name columns frozen left.
- **26c — Critical Path Notes layout** top to bottom: auto-generated plain-language summary, summary block (project name, end date, counts), critical path tasks table, tasks delaying the project (subset of critical with delay > 0), top 5 near-critical (lowest non-zero float), overdue incomplete tasks, recently completed late (last 30 days), recently completed early (last 30 days), dependency warnings.
- **26d — Demo projects:** `small_demo.json` (7 tasks, DAL only) and `npde_demo.json` (~30-50 multi-location, currently 13-task starter pending expansion).
- **26e — Logging:** mandatory rotating file at `.logs/gantt_builder.log`. 10 MB, last 5 kept. Default level `INFO`. Always on (no setting required).

---

## Open inline decisions confirmed late

- **Q8d parent cascade overwrite vs preserve:** **preserve.** Parent completion cascades to descendants, but descendants with their own earlier `actual_completion_date` retain that earlier date (don't destroy real history). Confirmed by user on resume.

- **License field:** **MIT.** Confirmed during demo-readiness scoping.

- **Real holiday seeding for demos:** **yes, seed real 2026-2027 from `holidays` library** in `examples/npde_demo.json`. Authorized during demo-readiness scoping.

---

## What the user is targeting post-grilling

- **Demo audience:** external customers / cross-team handoff.
- **Data sourcing:** public web only. Never TI internal data in the public repo.
- **Commit cadence:** per-feature commits.
- **Path:** A (autonomous go-mode) with checkpoint reviews at natural boundaries.

---

---

## Implementation-phase addenda

Decisions made during the autonomous implementation push (after the original Q1–Q26 grilling session).

## Q27 — Baseline fields on Task

**Decision:** Add `baseline_start: date | None = None` and `baseline_finish: date | None = None` to the Task model. Provide a `set_project_baseline(project, overwrite=False)` API that snapshots current `computed_start` / `computed_finish` into the baseline fields for every task. The baseline never changes when delays or completion shift the live schedule — it represents the user-committed plan for variance reporting.

**Why:** Project managers expect a "baseline" reference in any Gantt tool (MS Project, Primavera, etc.). Without a stored baseline, the Gantt only shows current state; users can't tell whether a task is running ahead/behind the original plan. Adding baseline lets Excel surface "Baseline Start" / "Baseline Finish" alongside "Computed Start" / "Computed Finish" for variance analysis.

**Mechanics:** `set_project_baseline()` runs the scheduler, then for each task: if `baseline_start is None` (or `overwrite=True`), set `baseline_start = computed_start` and `baseline_finish = computed_finish`. The baseline values persist in JSON and survive saves. Re-baselining is allowed via `overwrite=True` (e.g., after scope changes accepted).

**Visible at:** frozen-pane columns in Day View and Week View, plus Schedule Calculations sheet.

---

## Q28 — Column header naming for Cycle Time

**Decision:** Change "Cycle Time" column header to **"Cycle Time (Days)"** in both Day View / Week View frozen pane AND Schedule Calculations sheet. JSON field name stays `cycle_time_days`.

**Why:** When viewing the Gantt without the JSON schema in mind, "Cycle Time" alone is ambiguous (days? hours? working days?). The "(Days)" suffix in the header eliminates that ambiguity for end users. Internal field name remains `cycle_time_days` for consistency with code.

---

## Q29 — Real holiday seeding for demo projects

**Decision:** Seed real 2026–2027 holidays from the Python `holidays` library into both `examples/small_demo.json` and `examples/npde_demo.json`. Mark each entry with `source: "seeded"` so future re-seed operations can detect them as library-derived.

**Why:** Demonstrates the per-location holiday model authentically. With real holidays:
- `small_demo` has 27 US holidays.
- `npde_demo` has 173 holidays across DAL (27), MLA (41), TAI (46), FR-BIP (24), AIZU (35).

Real holidays push working-day task dates, exercise the holiday rendering in Excel, and surface multi-location holiday overlap in column headers (e.g., Christmas observed by DAL + FR-BIP + AIZU).

---

## Q30 — Parent-aware scheduling hardening

**Decision:** The scheduler must honor parent manual starts, parent dependencies, and dependencies on parent predecessors.

**Mechanics:** Descendant leaves inherit manual-start floors and dependency floors from their ancestor parents. A dependency on a parent predecessor uses that parent's rolled-up descendant schedule. The leaf topological order expands parent predecessors into their descendant leaves so rollups are available before dependent leaves are scheduled.

**Validation:** Parent cycles, dependencies on descendants, and dependencies on ancestors are logical validation errors because they fight the parent/descendant rollup graph.

**Status:** Implemented in the pre-Step-6 hardening pass and covered by tests.

---

## Q31 — Overdue tail rendering extends bar to today

**Decision:** For an incomplete task where `today > effective_finish`, the Day View renders a red "overdue" segment from `effective_finish + 1` through `today` (inclusive). Visually, this extends the bar past where it was supposed to end to convey "we should have been done by X but we're at Y."

**Why:** Without this tail, an overdue task would look the same as a current task that finished today. The red tail makes overdue tasks immediately visible at a glance. The Critical Path Notes sheet also lists overdue tasks separately.

---

## Q32 — Today vertical line implementation

**Decision:** Today appears in both the Day View column header (yellow fill `#FFF8C4`) AND as a thick black left border on every body cell in today's column. The body-cell border is implemented by precomputing every status × critical × today format combination (~30 distinct formats). Empty cells in today's column receive a `empty_today` format that combines the yellow fill with the black left border.

**Why:** A header-only indicator is easy to miss when scrolling through hundreds of tasks. The vertical line on every body cell makes today findable from anywhere on the sheet.

---

## Q33 — Checkpoint 2 visual-review iteration

**Decision:** Accept the user-requested checkpoint polish:

- Rename the USA site code to **DAL** while retaining US holiday seeding.
- Use planned blue `#8FB6E1` and holiday gray `#B0B0B0` for better Excel readability.
- Add a frozen-pane **Dependencies** column using compact numeric IDs.
- Add a first worksheet, **Chart Key & Info**, with working weeks, color legend, critical-path explanation, today-line explanation, and frozen-pane guide.
- Use the **long pole** as the red critical-path display set while retaining CPM `total_float` values in Schedule Calculations.

**Why:** The first visual review showed that external users need immediate context inside the workbook itself, and strict float-only critical display was less useful than the visible gating chain for this scheduling model.

---

## Q34 — Project-timezone audit/export timestamps

**Decision:** Save timestamps, snapshot names, Excel export filenames, and `last_export.at` use `project.project.timezone` when possible. If the configured IANA timezone is unavailable, the system falls back to the host local timezone rather than failing a save/export path.

**Why:** The schema says project timezone governs filenames and audit metadata. This keeps generated artifacts consistent even when the app runs on a machine in a different timezone.

---

## Q35 — Chronological Gantt row order

**Decision:** Day View and Week View rows sort chronologically by scheduled dates, not by task ID or JSON insertion order. Task IDs remain stable creation identifiers and are never renumbered for display.

**Example:** If a user creates `TASK-013` and its computed schedule belongs between `TASK-009` and `TASK-010`, the Gantt views display it between those tasks while keeping the ID `TASK-013`.

**Why:** The Excel Gantt is a timeline-first artifact. Chronological row order makes the workbook easier to scan without sacrificing stable IDs for dependencies, audit history, and references.

---

## Cross-references

- [DESIGN.md](DESIGN.md) — architecture-level rationale, organized by topic.
- [API.md](API.md) — Python API contract, function signatures, exception types.
- [JSONFILE.md](JSONFILE.md) — JSON schema reference, every field, every type.
- [EXCELBUILDER.md](EXCELBUILDER.md) — Excel output spec, sheets, columns, colors.
- [STREAMLIT.md](STREAMLIT.md) — UI spec, layout, workflows.
- [HANDOFF.md](HANDOFF.md) — resume-from-here document for next session.
