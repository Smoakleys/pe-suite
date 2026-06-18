# Executive Changes Summary

Every push to `https://github.com/Frosty-STI/PMSuite.git`, with a detailed explanation of what changed and why.

---

## Push 1 -- `969681c` -- 2026-05-12

**Initial commit**

Created the GitHub repository with a placeholder README. Established the `main` branch and remote origin for the PMSuite project.

---

## Push 2 -- `10a294d` -- 2026-05-14

**Walking-skeleton scaffold for PMSuite Gantt Builder**

Laid the full project foundation: package structure (`gantt_builder/`), Pydantic v2 models for Project/Task/Dependency/Settings, forward-pass scheduler with FS dependencies, two-tier validation (structural + logical), atomic JSON I/O with rotating snapshots, stub Excel builder with 5 sheets, Streamlit read-only UI shell, CI workflow (GitHub Actions on Python 3.11/3.12), two example project files (`small_demo.json`, `npde_demo.json`), and 11 initial tests covering models, I/O round-tripping, and end-to-end pipeline.

**Why:** The walking skeleton establishes every layer of the architecture end-to-end so that subsequent feature commits add behavior to an already-running system rather than assembling disconnected pieces.

*26 files, +2,511 lines*

---

## Push 3 -- `b7c357d` -- 2026-05-14

**Add comprehensive design documentation**

Created 6 documentation files: API.md (Python API contract), EXCELBUILDER.md (Excel output spec), HANDOFF.md (resume-from-here for agents/developers), JSONFILE.md (JSON schema reference), MASTERECAP.md (all 26 grilling-session design decisions), STREAMLIT.md (UI spec with planned features).

**Why:** The design was produced through a structured grilling session (26 questions). Capturing every decision in durable documents ensures future contributors can understand not just what the code does but why each choice was made. MASTERECAP is the canonical decision log; the other docs are organized views of the same decisions by topic.

*6 files, +1,634 lines*

---

## Push 4 -- `e3bde5e` -- 2026-05-14

**Implement backward-pass CPM with total float and critical-path detection**

Added a full CPM backward pass to `critical_path.py`: computes late-start/late-finish for every task, derives total float, and marks tasks with float == 0 as critical. Completed tasks are excluded from the live critical path. Added `_subtract_days_in_calendar` helper to the scheduler for backward-pass calendar math. 8 tests covering float computation, critical set detection, and completed-task exclusion.

**Why:** Critical path analysis is the core value proposition for project managers. Without it, the Gantt is just a colored timeline. Total float tells PMs which tasks have slack and which are gating the project end date. (Design: Q17)

*3 files, +351 lines*

---

## Push 5 -- `3a61f29` -- 2026-05-14

**Implement full SS / FF / SF dependency types with lag**

Extended the scheduler's dependency-floor dispatcher from FS-only to all four CPM relationship types (Start-to-Start, Finish-to-Finish, Start-to-Finish) with positive and negative lag. Updated the backward-pass CPM to handle all four types. 12 tests covering each type with lag variations, cross-calendar-mode boundaries, and negative lead times.

**Why:** Real NPDE projects use SS (parallel start) and FF (synchronized finish) regularly. FS-only would force users to model parallel work with artificial lags and dummy tasks. (Design: Q3, Q8)

*3 files, +302 lines*

---

## Push 6 -- `f40e9dd` -- 2026-05-14

**Implement delay propagation engine with auto-catchup and undo**

New `delays.py` module with: `preview_auto_catchup` (dry-run), `apply_auto_catchup` (Option B per-task accurate static), `apply_manual_delay`, `undo_delay_batch`, and `is_auto_catchup_pending`. Added `CompletedTaskCannotBeDelayedError` to the error hierarchy. Fresh-project baseline initialization sets `last_auto_delay_run` to today without applying delays. 19 tests covering multi-day catch-up, idempotency, completion freeze, manual delay, undo with edit-guard, and fresh-project initialization.

**Why:** Delays are first-class state in PMSuite, not derived. The auto-catchup-on-load model means projects "drive themselves when opened" -- a PM who was away for a week sees exactly how many days each task slipped. The undo mechanism builds trust. (Design: Q9, Q11, Q24)

*4 files, +628 lines*

---

## Push 7 -- `1829fa5` -- 2026-05-14

**Implement parent completion cascade with preserve-earlier-children rule**

New `completion.py` module with `mark_task_complete`, `unmark_task_complete`, and `undo_complete_batch`. When a parent is marked complete, all descendants are cascaded. Children with their own earlier `actual_completion_date` retain their earlier date (real history is preserved). Added `all_descendant_ids` and `all_descendant_leaf_ids` helpers to the Project model. 15 tests covering cascade, preserve-earlier, undo, and the unmark single-task path.

**Why:** In NPDE workflows, marking a phase complete should cascade to sub-tasks automatically. But a sub-task that finished early (e.g., wafer fab completed ahead of schedule) should keep its real date -- overwriting it would destroy audit history. (Design: Q8, Q8d)

*5 files, +489 lines*

---

## Push 8 -- `38a85a2` -- 2026-05-14

**Add Cycle Time + Baseline Start + Baseline Finish to frozen panes**

New `baseline.py` module with `set_project_baseline` (snapshots computed dates into `baseline_start`/`baseline_finish` per task). Added baseline fields to the Task model. Updated Excel builder to include Cycle Time (Days), Baseline Start, and Baseline Finish in the frozen-pane metadata columns of Day View and Week View. Seeded baselines into both demo projects. 5 baseline tests.

**Why:** Project managers expect a baseline reference (the original plan) alongside the live schedule so they can see variance at a glance. "Cycle Time (Days)" header eliminates ambiguity about units. (Design: Q27, Q28)

*7 files, +442 lines*

---

## Push 9 -- `c824203` -- 2026-05-14

**Implement full Option E Excel rendering**

Major expansion of `excel_builder.py`: segmented cell coloring (planned blue, completed green, delayed orange, overdue red), critical-path dark-red border stripe, today vertical line (thick black left border on every body cell), multi-line date column headers with weekday + ISO date + holiday names per location, per-row weekend/holiday gap shading for working-day tasks, e-day tasks rendering continuous, parent summary bars in dark gray. Seeded real 2026-2027 holidays from the Python `holidays` library into both demo projects (27 US holidays for small_demo, 173 across 5 locations for npde_demo).

**Why:** The Excel workbook is the primary deliverable -- what gets emailed to stakeholders and reviewed in meetings. Option E (segmented static cell coloring) was chosen because it scales, doesn't require merged cells, and carries all status encoding in color alone. Real holidays make the demo authentic. (Design: Q15, Q29)

*3 files, +1,324 lines*

---

## Push 10 -- `6dbc79a` -- 2026-05-14

**Refresh documentation to reflect steps 1-5 implementation state**

Updated API.md (new delay/completion/baseline function signatures), EXCELBUILDER.md (current rendering status), HANDOFF.md (full file manifest, test counts, what works today), JSONFILE.md (baseline field documentation), MASTERECAP.md (Q27-Q29 implementation addenda). All docs now accurately describe the implemented system rather than the planned design.

**Why:** Documentation that describes the plan rather than the reality becomes misleading. After shipping 5 feature steps in rapid succession, the docs needed to catch up so the next agent or contributor starts from truth.

*5 files, +367/-105 lines*

---

## Push 11 -- `309c66b` -- 2026-05-17

**Checkpoint 2 iteration: USA->DAL rename, long-pole detection, demo parallel tasks, Excel polish**

Renamed the USA site code to DAL (Dallas) across all code, tests, and data. Replaced strict float-only critical path display with long-pole detection (terminal unfinished leaves + their transitive gating chain). Added a Chart Key & Info sheet with color legend, working-week reference, and frozen-pane guide. Added Dependencies column to frozen panes. Updated demo projects with parallel tasks and richer structure. Migration scripts in `scripts/`.

**Why:** The Checkpoint 2 visual review by the user revealed that (a) "USA" was too generic -- DAL identifies the specific site, (b) strict float-zero critical display missed the obvious gating chain due to working-day boundary snapping, and (c) external users need context inside the workbook itself. (Design: Q33)

*14 files, +622/-210 lines*

---

## Push 12 -- `0e838cc` -- 2026-05-17

**Harden Step 5 readiness before Streamlit editing**

Pre-Step-6 hardening pass: parent-aware scheduling (parents inherit dependency floors and manual-start floors to descendants), project-timezone timestamps for saves/exports/snapshots, expanded validation (parent-cycle-time, parent-descendant dependency conflicts, unanchored leaf detection), `time_utils.py` for timezone-aware `project_now()`, LICENSE file (MIT), broader test coverage across validation, dependencies, Excel structure. 95 tests passing.

**Why:** Before building the editing UI, the backend needed to be bulletproof. Parent-aware scheduling was partially implemented; this commit closed the gaps so that any edit the Streamlit UI allows will schedule correctly. Adding the license formalized the open-source intent. (Design: Q30, Q34)

*23 files, +794/-152 lines*

---

## Push 13 -- `e0998d2` -- 2026-05-17

**Sort Gantt views chronologically**

Day View and Week View rows now sort by computed schedule dates (primary: computed_start; ties: parent-above-children, then finish date, then stable ID). Task IDs remain stable creation identifiers -- a later-created TASK-013 appears between TASK-009 and TASK-010 when its dates belong there. Updated all 6 documentation files to reflect this decision. Additional Excel structural tests.

**Why:** The Excel Gantt is a timeline-first artifact. ID-ordered rows would scatter tasks across the timeline, making the chart hard to read. Chronological order makes the workbook scannable without sacrificing stable IDs for references. (Design: Q35)

*9 files, +205/-46 lines*

---

## Push 14 -- `bc38ea7` -- 2026-05-17

**Restore compact Gantt timeline widths**

Reduced Day View date column width from 6 to 4 and Week View from 12 to 10. Added structural tests asserting column widths match the spec.

**Why:** Wider columns from a prior refactor pushed the timeline too far right, requiring excessive horizontal scrolling. The compact widths match the EXCELBUILDER.md spec and keep more of the timeline visible on screen.

*2 files, +26/-7 lines*

---

## Push 15 -- `2b24ce7` -- 2026-05-17

**Add Step 6 editing API primitives**

New `editing.py` module with `add_task` (auto-generates next TASK-NNN ID, advances counter, skips gaps), `update_task` (validates updated model, rejects ID renames), `delete_task` (blocks if dependents or children exist), `add_dependency` (rejects self-deps and parent-hierarchy conflicts, upserts), `remove_dependency` (idempotent). Added `TaskDeletionBlockedError` to the error hierarchy. All 5 functions re-exported via `api.py`. 11 tests.

**Why:** The Streamlit editing surface needs mutation primitives that enforce the data model's invariants (stable IDs, no orphan dependencies, no parent-cycle-time conflicts). Building them as a separate API layer means the UI can't accidentally bypass validation. This is the foundation for Step 6.

*7 files, +372/-13 lines*

---

## Push 16 -- `6348aca` -- 2026-05-17

**Step 6: Streamlit editing surface, New Here? walkthrough, button descriptions**

Full rewrite of `ui/streamlit_app.py` from read-only walking skeleton to complete editing surface: `st.session_state` persistence for project + dirty flag, task add/edit/delete via expander-based editors, dependency picker with add/remove and type/lag selection, mark-complete wired to cascade API, auto-catchup-on-load prompt with Apply/Skip/Undo, dirty-state badge with browser `beforeunload` warning, New Project form, project switcher with Cancel/Discard/Save & Switch dialog, sidebar settings panel, Set Baseline button, Dependency Explanation expander.

Added concise descriptions under each action button (Validate, Save, Build Excel, Set Baseline). Added "New Here?" walkthrough -- a pale green banner expanding into a 10-step guide grounded in MASTERECAP design decisions (Q1-Q35).

Created `EXECUTIVE_CHANGES_SUMMARY.md` with backfilled entries for all prior commits. Updated HANDOFF.md roadmap with Step 10 (Playwright UI verification) and Step 11 (Final Walkthrough Refresh).

**Why:** Step 6 is the transition from "backend tool" to "usable application." Without an editing surface, users must hand-edit JSON -- which defeats the purpose of building a UI. The walkthrough ensures first-time users can orient themselves without reading 6 documentation files. Button descriptions reduce the "what does this do?" friction for non-technical users.

---

## Push 17 -- `b9dee2b` -- 2026-05-18

**Reorder roadmap: Playwright verification before holiday editor**

Moved Playwright UI verification from Step 10 to Step 7 in the HANDOFF.md roadmap. Holiday editor, demo expansion, and test backfill shift to Steps 8-10. Step 11 (Final Walkthrough Refresh) unchanged.

**Why:** Screen out bugs in the Step 6 editing surface before adding feature complexity. The user's philosophy is to iron out issues before passing to users, not to have users discover bugs. Running Playwright against the current UI before the holiday editor ensures a stable foundation for future features.

---

## Push 18 -- `228bf7e` -- 2026-05-18

**UI polish pass: save state indicators, button layout, beforeunload fix, HANDOFF hardening**

Streamlit UI changes:
- Capitalized "Timezone" in the project subtitle.
- Restructured action buttons: buttons render in one row (all level), descriptions render in a second row below. This fixes the Set Baseline button being pushed down by its longer caption text.
- Updated Set Baseline description to "Record each task's current scheduled start and finish as the original baseline dates."
- After clicking Set Baseline, explanatory text appears below the button row describing what happened, plus descriptions of the Auto-delay and Keep Local Snapshots sidebar settings.
- Added save state indicator below the button row: orange italic "Unsaved changes" when dirty, green italic "All changes saved" when clean. Removed the old "* Unsaved changes" title badge.
- Fixed `beforeunload` dialog firing on Save click. Introduced a `_pmsuiteAllowReload` JavaScript flag on the parent window: the beforeunload handler checks this flag and allows navigation silently when set. Save, Cancel, Discard & Switch, and Save & Switch all set the flag before calling `st.rerun()`. Tab close and manual navigation still trigger the warning dialog.

Documentation changes:
- HANDOFF.md: strengthened the EXECUTIVE_CHANGES_SUMMARY.md update requirement from a bullet point to a mandatory, explicit instruction for all agents.
- EXECUTIVE_CHANGES_SUMMARY.md: backfilled push 16 and 17 hashes, added this entry.

**Why:** The user's design principle is to be as friendly to the user as possible — explaining how the tool works without getting in the way. The save state indicator gives instant visual feedback. The button layout fix keeps the UI clean. The beforeunload fix eliminates a confusing dialog on the safest action (Save). The HANDOFF hardening ensures no future agent skips the executive changelog.

---

## Push 19 -- `abecad1` -- 2026-05-18

**Step 7: Playwright UI verification suite (in progress) + documentation updates**

Playwright test infrastructure:
- Created `tests/fixtures/npde_playwright_test_fixture.json` — copy of npde_demo.json with dates shifted to provide both past (2025) and future (post-9/18/2026) tasks. TASK-003 left incomplete/overdue to trigger auto-catchup. TASK-014 "Filler task" bridges 438 e_days.
- Created `tests/playwright_helpers.py` — 30+ composable async helpers for all UI interactions (server lifecycle, page navigation, task CRUD, dependency management, action buttons, auto-catchup, project management, settings, assertions).
- Created `tests/test_streamlit_playwright.py` — 23 tests across 10 classes covering 18 golden-path flows: showcase, load project, add/edit/delete task, delete-blocked, add/remove dependency, mark complete, validate (clean + errors), save + dirty state, build Excel, set baseline, auto-catchup apply/undo/skip, new project creation, project switching (cancel/discard/save), manual start toggle, settings (auto-delay, snapshots).
- Created `PLAYWRIGHT_SCREENING.md` — design decisions from 17-question grilling session, current coverage table with assertion depth per test, known coverage gaps, stabilization status, running commands.
- Updated `pyproject.toml` — added `test-ui` optional dependency group (`pytest-playwright>=0.4`), added `playwright` pytest marker.

Documentation updates:
- Updated HANDOFF.md: Step 7 marked as "In progress" with description of what's written vs. what needs verification. Added Step 7a for the "Complete?" checkbox UI change. Updated local layout to include new Playwright files.
- Updated PLAYWRIGHT_SCREENING.md: added full coverage table, known gaps section, stabilization status.

Post-initial-write hardening:
- Added automatic screenshot-on-failure: `page_and_project` fixture uses `pytest_runtest_makereport` hook to detect failures and save PNGs; standalone tests (Showcase, AutoCatchup, NewProject) use try/except wrappers. Screenshots saved to `test-results/screenshots/` (gitignored).
- Fixed `test_build_excel` assertion depth: now verifies a new `.xlsx` file was created on disk using `find_latest_excel()`, not just checking for UI alerts.
- Updated `.gitignore` with `test-results/` exclusion.

**Stabilization note:** First test run was 3/23 passing due to selector/timing mismatches with Streamlit's DOM. Helpers were rewritten to target correct elements (`<summary>` for expanders, `data-testid` attributes, auto-catchup dismissal). A full green run has **not yet been confirmed** — the next agent must run the suite and debug remaining failures before committing as complete.

**Why:** The user's philosophy is to screen out bugs before adding feature complexity. The Playwright suite verifies the full round-trip (click → session state → JSON on disk → reload) for every editing flow in the Step 6 UI. Writing tests before the holiday editor ensures a stable foundation.

---

## Push 20 -- `91695ac` -- 2026-05-20

**Steps 7a + 7b complete: "Complete?" checkbox UI + Playwright suite 25/25 green**

This push delivers two milestones: the "Complete?" read-only indicator on collapsed task rows (Step 7a) and a fully passing Playwright UI verification suite (Step 7b).

**Step 7a — "Complete?" checkbox on collapsed task rows:**
- Added `st.columns([8, 2])` layout in `_render_task_table`: the 80%-width left column holds the task expander, the 20%-width right column holds a disabled `st.checkbox("Complete?")` reflecting `task.is_complete`.
- Fixed Streamlit widget caching bug: disabled checkboxes with `key=` retain stale session-state values across reruns. Added `st.session_state[key] = task.is_complete` before rendering to force-sync the indicator on every rerun.
- URL query parameter project loading: added `st.query_params` support in `main()` so tests can load projects via `?project=projects/filename.json` without using the selectbox.

**Step 7b — Playwright suite stabilization (25/25 green):**

Three root causes were identified and fixed:

1. **Subprocess pipe buffer deadlock** (critical): `start_streamlit()` used `subprocess.PIPE` for stdout/stderr. After ~64KB of Streamlit log output filled the pipe buffer, the server process blocked on `write()` and stopped serving WebSocket connections. Fix: redirect stdout/stderr to log files in `test-results/`.

2. **Locator ambiguity from dependency text**: `has_text="TASK-004"` matched both TASK-004's expander AND TASK-005's expander (because TASK-005 depends on TASK-004, and Streamlit renders hidden dependency text in the DOM even when collapsed). Fix: `_task_locator()` helper uses `has_text=f"{task_id} --"` — the double-dash format uniquely matches the expander summary line.

3. **Streamlit checkbox off-viewport clicks**: Streamlit hides native `<input type="checkbox">` elements off-screen for styling, making them unclickable even with `force=True`. Fix: `evaluate("el => el.click()")` dispatches the DOM click directly, bypassing Playwright's viewport coordinate check.

Additional fixes: `triple_click()` → `click(click_count=3)` (API mismatch), viewport set to 1920×4000 for 14-task pages, form wait for New Project, broader test cleanup patterns, simplified reload-dependent assertions to JSON verification.

Test infrastructure: session-scoped browser context with per-test pages, automatic screenshot-on-failure with setup-failure capture, `run()` helper for async-to-sync bridging.

**Why:** The Playwright suite is the safety net for all future changes. Every editing flow (task CRUD, dependencies, completion cascade, auto-catchup, project switching, settings, Excel export, baseline) is now verified end-to-end. The "Complete?" indicator gives at-a-glance visibility without opening each expander.

---

## Push 21 -- `4689601` -- 2026-05-20

**Step 7c complete: Child task hierarchy in Streamlit + Excel**

This push delivers the UI and rendering support for arbitrarily deep parent/child task nesting. The backend hierarchy (`parent_id`, `has_subtasks()`, cascade, floor propagation) was already complete — this step adds the user-facing creation controls and the Excel visual grouping.

### Streamlit UI changes (`ui/streamlit_app.py`):

1. **"Add Child Task" button** inside each task's expander. Pre-fills `parent_id`, `completion_location`, and `calendar_mode` from the parent task. Creates a leaf child with `cycle_time_days=1` and `manual_start_date=today` (or parent's manual start). Enables arbitrarily deep nesting — a child task's expander also has an "Add Child Task" button.

2. **"Parent task" dropdown** in the top-level "Add new task" form. Shows all existing task IDs with names; defaults to "(none)" for root tasks. Combined with the existing parent picker in the task editor (for re-assigning parents after creation), users now have three ways to set hierarchy: Add Child Task button, Add Task form parent dropdown, and task editor parent picker.

3. **Hierarchy-ordered task display.** Tasks are shown in pre-order tree walk (parent above children), with depth-based whitespace indentation in the expander labels. Root tasks maintain their original insertion order; children appear directly below their parent.

### Excel changes (`gantt_builder/excel_builder.py`):

1. **Row grouping with outline levels** on Day View and Week View sheets. Child rows get `outline_level = hierarchy_depth` (level 1 for direct children, level 2 for grandchildren, etc.). Parent rows stay at level 0. `outline_settings(symbols_below=False)` puts the `+`/`-` collapse toggle on the parent row above the group, not below.

2. **Hierarchy-aware row ordering.** `_gantt_task_order()` changed from flat chronological sort to a pre-order tree walk: root tasks sorted chronologically, each parent followed immediately by its children (also chronological among siblings), recursively. This ensures child rows are always adjacent to and below their parent.

3. **Indented task names.** The frozen-pane Name column now indents child task names by 2 spaces per hierarchy level (`"  " * level + name`), making the tree structure visible even without the outline grouping.

**Why:** NPDE programs need arbitrarily granular task decomposition — "Wafer Fab" breaks into "Lot 1 processing" and "Lot 2 processing," each of which breaks into sub-steps. The flat task list forced all tasks to one level, making the Gantt noisy for executives and lacking detail for engineers. Excel row grouping solves both: collapsed groups for the executive view, expanded detail for engineering review. The Streamlit "Add Child Task" button makes creating hierarchy as easy as clicking a button rather than manually setting parent_id.

---

## Push 22 -- `d6e3b6b` -- 2026-05-20

**Step 7c follow-up: NPDE demo hierarchy, bug fix, UI polish attempts, README rewrite**

### Changes:

1. **NPDE demo expanded to 17 tasks with parent/child hierarchy.** Added three parent groupings to `examples/npde_demo.json`: "Post-Fab Processing" (TASK-014, parent of TASK-004 Assembly + TASK-011 Local Assembly), "Final Documentation" (TASK-015, parent of TASK-008 Datasheet + TASK-012 TID Report + TASK-013 NDD Report), and two sub-lots under TASK-003 Wafer fab (TASK-016 Lot 1 + TASK-017 Lot 2 with SS+3 dependency). Demonstrates three levels of hierarchy for visual inspection of Excel row grouping.

2. **Bug fix: "Add Child Task" now auto-clears parent's `cycle_time_days`.** Previously, clicking "Add Child Task" on a leaf task created the child correctly but left the parent's `cycle_time_days` set, causing `PARENT_HAS_CYCLE_TIME` validation errors. The button handler now calls `api.update_task(project, task.id, cycle_time_days=None)` when the task transitions from leaf to parent.

3. **UI polish attempts (partially successful, two issues remain):**

   - **Copy-able task ID:** Added `st.code(task.id)` at the top of every task editor, providing a monospace copy-able field for the task ID.
   
   - **Disabled checkbox cursor fix:** Injected CSS (`cursor: default !important` on `div[data-testid='stCheckbox']:has(input[disabled])`) to remove the red cancel/not-allowed cursor icon on the read-only "Complete?" indicators.
   
   - **Parent cycle time field:** Changed from `st.text("Cycle Time: (derived from children)")` to `st.text_input(..., disabled=True)` for visual consistency with the `st.number_input` on leaf tasks.

4. **Two unresolved UI issues flagged in HANDOFF.md:**

   - **"Is Complete" checkbox inside task expander reportedly does nothing when clicked.** The completion toggle (`st.checkbox("Is Complete")`) is interactive (not disabled) but the user cannot complete tasks. May be a Streamlit widget key conflict with the disabled "Complete?" indicator sharing a naming pattern, or a rerun timing issue with the Apply button flow.
   
   - **Parent task editors still visually differ from leaf task editors.** The `st.text_input(disabled=True)` for parent cycle time does not match the font/size of `st.number_input` on leaf tasks. Needs CSS override or a different widget approach.

5. **README.md rewritten for new-machine setup.** Step-by-step instructions covering: prerequisites, clone, venv creation (Windows PowerShell/CMD/macOS/Linux), `pip install -e ".[dev]"`, test verification (`95 passed`), Streamlit launch with `--server.headless true`, demo exploration. Added troubleshooting section for common issues (streamlit not on PATH, email prompt, PowerShell red stderr, import failures).

**Why:** The NPDE demo with real hierarchy is essential for visual verification of Excel row grouping and Streamlit hierarchy display. The README rewrite ensures smooth transfer to a new laptop — every command is explicit with platform-specific variants. The unresolved UI issues are documented so the next session can tackle them without re-discovering them.

---

## Push 23 -- `42ce709` -- 2026-05-31

**Step 7d: UI polish -- uniform task labels, hierarchy indentation, immediate completion toggle, parent editor consistency**

Four UI fixes applied to `ui/streamlit_app.py`:

1. **Uniform task text rendering.** Removed the `[P]` prefix on parent tasks and the `(child of TASK-XXX)` suffix on child tasks from expander labels. All tasks now render with the same format: `TASK-XXX -- Name`. No markdown is used in task label rendering. Replaced the bold markdown `st.markdown("**Dependencies (predecessors)**")` inside task editors with plain `st.text()`.

2. **Hierarchy indentation with em-spaces.** Child tasks are indented by 4 em-spaces (` `) per depth level in the expander label. Children of children indent further, making the tree structure visually obvious without needing prefixes or suffixes. Em-spaces were chosen because they render at consistent width and are not collapsed by HTML/Streamlit rendering.

3. **"Is Complete" checkbox now works immediately.** Previously, toggling the "Is Complete" checkbox inside a task expander required clicking the separate "Apply changes" button to take effect. The completion toggle now fires immediately on checkbox click: checking it calls `mark_task_complete` with today's date (per design Q8a auto-fill), unchecking calls `unmark_task_complete`. The completion date is shown read-only for already-complete tasks; date changes for completed tasks still go through Apply.

4. **Parent task editors match leaf task editors.** Parent tasks previously used `st.text_input(disabled=True)` for the Cycle Time field while leaf tasks used `st.number_input`. Both now use `st.number_input` (parents show 0, disabled) with a caption "Derived from children" below. The widget chrome is visually identical.

**Why:** The user flagged that tasks rendered inconsistently (different prefixes and suffixes depending on parent/child status), making the task list noisy. The "Is Complete" checkbox not responding to clicks was a known issue since Push 22 -- the root cause was that completion was gated behind the Apply button, which is non-obvious UX. Making it immediate matches user expectation. The parent editor mismatch (text_input vs number_input) was a visual inconsistency that made the UI feel unfinished.

---

## Push 24 -- `a2b9b53` -- 2026-06-01

**Step 8: Interactive Gantt chart rendering + visual redesign**

This push delivers the working Interactive Gantt editing surface. The Frappe Gantt custom component now renders inside the Streamlit UI with status-colored bars, dependency arrows, click/drag interactions, sidebar editing, and context menus. Three rendering bugs were diagnosed and fixed, and the visual theme was completely rewritten.

### Bugs fixed:

1. **`classList.add()` crash (fatal).** `_prepare_gantt_data()` builds CSS class strings with spaces (e.g., `"overdue critical"`). Frappe Gantt's `Bar.refresh()` calls `classList.add(custom_class)` which throws `InvalidCharacterError` on space-separated tokens. The entire chart crashed silently. **Fix:** `GanttComponent.jsx` temporarily monkey-patches `DOMTokenList.prototype.add` to split space-separated tokens, restored in a `finally` block.

2. **`calc(100vh - 200px)` in iframe (height collapse).** The container used `100vh` for max-height, but inside a Streamlit iframe `100vh` starts at 0, producing `-200px`. Even error messages were invisible. **Fix:** Removed `maxHeight` and `overflowY` from the container; let `Streamlit.setFrameHeight()` size the iframe.

3. **CSS specificity loss (bars invisible).** Frappe's CSS uses `.gantt .bar-wrapper .bar { fill: var(--g-bar-color) }` (specificity 0,3,0). The theme used `.gantt .bar` (0,2,0) which loses. `--g-bar-color` defaulted to `#fff` — white bars on white background. **Fix:** Complete CSS rewrite overriding Frappe CSS variables at `:root` and matching specificity on all bar-fill selectors.

### Visual redesign ("Industrial Precision" theme):

- **Status colors:** Steel blue (planned), teal-green (completed), amber (delayed), signal red (overdue), dark charcoal (parent tasks). Critical path bars have dark red border stroke.
- **Grid:** Whisper-weight hairlines (`stroke-width: 0.3`), subtle alternating row bands, barely-there column hover.
- **Dependency arrows:** Light gray at 60% opacity with rounded joins — recede behind task bars.
- **Labels:** White text on colored bars with subtle stroke outline; dark text when overflow. DM Sans font family.
- **Today marker:** Dark vertical line with date badge.
- **Popup:** Crisp info card with title/subtitle/details hierarchy, proper shadow.
- **Selected state:** Blue outline with soft glow.
- **Context menu:** Right-click on bars shows Edit / Mark Complete / Add Child / Delete.

### Frappe Gantt option tuning:

- `bar_height: 24` (down from 28), `padding: 16`, `bar_corner_radius: 4`
- `column_width` responsive per view mode (Day: 32, Week: 120, Month: 140)
- `upper_header_height: 36`, `lower_header_height: 28` (compact headers)
- `scroll_to: "today"` (was "start" — showed empty past dates instead of current bars)
- `arrow_curve: 6` for smoother dependency connectors

### Files changed:

| File | Change |
|------|--------|
| `components/gantt_chart/frontend/src/GanttComponent.jsx` | classList.add patch, removed broken maxHeight, tuned Frappe options, improved popup/context menu |
| `components/gantt_chart/frontend/src/gantt-theme.css` | Complete rewrite: CSS variable overrides, specificity-matched bar fills, grid/arrow/label/popup/scrollbar styling |
| `components/gantt_chart/frontend/build/` | Rebuilt Vite production bundle |
| `.gitignore` | Added negation for `components/gantt_chart/frontend/build/` (needed at runtime) |
| `HANDOFF.md` | Updated: Step 8 no longer blocked, documented fixes, known bugs, next-session instructions |
| `EXECUTIVE_CHANGES_SUMMARY.md` | This entry |

**Why:** Step 8 was blocked since Push 23 by a "Component Error" message. The root cause was three compounding bugs: a DOM API crash from space-separated CSS classes, a CSS calc that produced negative heights in an iframe context, and a specificity loss that made all bars invisible. Fixing all three and rewriting the visual theme transforms the Gantt from non-functional to a usable interactive editing surface. The remaining bugs (dependency arrow creation, scrollbar visibility, visual polish) are incremental fixes, not blockers.

---

## Push 25 -- `eb4e5c9` -- 2026-06-02

**Fix horizontal scrollbar clipped by Streamlit iframe boundary**

The Gantt chart's horizontal scrollbar was invisible because the Streamlit component iframe was sized too small to include it. This push fixes the root cause and documents a new regression (context menu broken).

### Root cause analysis:

`StreamlitComponentBase.componentDidMount()` and `.componentDidUpdate()` both call `Streamlit.setFrameHeight()` with no arguments, which auto-detects from `document.body.scrollHeight`. This measurement (776px) does not include the 12px horizontal scrollbar that the browser renders below the `.gantt-container` content. The iframe was sized to exactly the content height, clipping the scrollbar by 8px (`room_below: -8px`).

### Fix (GanttComponent.jsx):

1. **Skipped `super.componentDidMount()` and `super.componentDidUpdate()`** — these only called `setFrameHeight()` with no args (the source of the clipping).
2. **Added `_setFrameHeightWithScrollbar()` helper** — measures `.gantt-container.offsetHeight + 20` and passes the explicit value to `Streamlit.setFrameHeight()`. The 20px buffer accounts for the scrollbar track (12px) plus margin.
3. **Both `_buildGantt()` and the `else` branch in `componentDidUpdate`** now call this helper, ensuring the iframe is always sized correctly whether or not the chart rebuilds.

### Verification:

Playwright-driven diagnostic confirmed: `room_below: 12px` (was -8px), `innerHeight: 796` (was 776), programmatic scrolling works (`scrollLeft` 700 → 1000), and the Gantt renders correctly in both Week and Day view modes. User confirmed scrollbar is now visible.

### New regression discovered:

Right-click context menu on task bars no longer appears. The context menu code is intact — the issue is likely event coordination or `position: fixed` coordinate mapping within the resized iframe. Documented in HANDOFF.md with hypotheses and debug path for the next session.

### Files changed:

| File | Change |
|------|--------|
| `components/gantt_chart/frontend/src/GanttComponent.jsx` | Skip base class setFrameHeight(), add _setFrameHeightWithScrollbar() helper |
| `components/gantt_chart/frontend/build/` | Rebuilt Vite production bundle |
| `HANDOFF.md` | Updated status, replaced scrollbar bug with context menu bug, added fix documentation |
| `EXECUTIVE_CHANGES_SUMMARY.md` | This entry |

**Why:** The horizontal scrollbar is essential for navigating the Gantt chart timeline — without it users cannot see tasks beyond the initial viewport width. The fix was non-obvious because the naive approach (`document.documentElement.scrollHeight + 20`) caused a feedback loop inflating the iframe to 100K+ pixels. The stable fix measures the actual `.gantt-container` element height instead.

---

## Push 26 -- `95946c2` -- 2026-06-03

**Fix right-click context menu and suppress Frappe popup on right-click**

Diagnosed and fixed the right-click context menu issue on Gantt task bars. The previous push (25) reported this as a regression from the scrollbar fix, but Playwright-based diagnosis with console instrumentation proved the context menu handler was firing correctly and the menu was rendering. The actual problem was Frappe Gantt's internal event handling interfering with right-click: its `mouseup` handler fires for ALL mouse buttons and shows a popup that overlaps the context menu, and its `mousedown` handler starts drag state on right-click.

### Root cause analysis:

Frappe Gantt v1.2.2's `bar.js` binds a `mouseup` handler on each bar group (`.bar-wrapper`) that fires for all mouse buttons, not just left-click. On right-click, this handler calls `show_popup()`, displaying the Frappe info popup on top of or alongside the custom context menu. Additionally, the `mousedown` handler in `index.js` sets `is_dragging=true` and `bar_being_dragged=false` on right-click, polluting Frappe's internal drag state.

### Fix (GanttComponent.jsx):

1. **Capture-phase `mousedown` listener on SVG** — added `svgEl.addEventListener("mousedown", (e) => { if (e.button === 2) e.stopPropagation(); }, true)`. This prevents Frappe's delegated mousedown handler from firing on right-click, so it never enters drag mode for button 2. Left-click drag (button 0) is completely unaffected because the guard only triggers for `e.button === 2`.

2. **`requestAnimationFrame` popup hide in `_handleContext`** — after setting the context menu React state, schedules `this.ganttInstance.hide_popup()` for the next animation frame. This runs after Frappe's `mouseup` handler has already called `show_popup()`, hiding the Frappe popup before the user sees it alongside the context menu.

### Diagnosis method:

Used the `/diagnose` skill with Playwright-based feedback loop. Added tagged `[DEBUG-ctx*]` console.log instrumentation to `_handleContext`, `_handleDocClick`, and `_buildGantt()`. Ran 4 automated tests: (1) direct right-click shows context menu, (2) Frappe popup suppressed, (3) left-click then right-click after Streamlit re-render, (4) context menu action click dismisses menu. All passed. Also probed: right-click on empty grid (no menu — correct), left-click drag still works after fix.

### Three new Gantt UX bugs documented (user-reported, not yet fixed):

| Priority | Bug | Summary |
|----------|-----|---------|
| P0 | Double-click add task | Double-clicking blank space on the Gantt chart does not add a task, despite the hint text saying it should. |
| P1 | Sidebar not reopened | Clicking "Hide sidebar" then "+ Add Task" does not reopen the sidebar. The add-task form is inside the sidebar, so it's invisible. |
| P2 | Cancel inconsistent | Clicking "Cancel" in the add-task sidebar sometimes doesn't reset to "Click a task bar to edit" state. |

### Files changed:

| File | Change |
|------|--------|
| `components/gantt_chart/frontend/src/GanttComponent.jsx` | Added capture-phase mousedown guard for button 2, added requestAnimationFrame popup hide in _handleContext |
| `components/gantt_chart/frontend/build/` | Rebuilt Vite production bundle |
| `HANDOFF.md` | Updated status, replaced context menu bug with three new UX bugs, added Bug 5 fix documentation |
| `EXECUTIVE_CHANGES_SUMMARY.md` | This entry |

**Why:** The right-click context menu (Edit / Mark Complete / Add Child / Delete) is the primary quick-action interface for the interactive Gantt. Without it, users must click a bar to open the sidebar editor, then navigate to the specific action — a much longer workflow. The fix is minimal and surgical: two event handlers that only affect right-click behavior, leaving all left-click interactions untouched.
