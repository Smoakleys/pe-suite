# Playwright Screening — Design Decisions & Test Plan

This document records every design decision from the grilling session that produced the Step 7 Playwright UI verification suite. Each decision is anchored to its question number (Q1-Q17).

## Purpose

Screen out bugs in the Step 6 Streamlit editing surface **before** adding feature complexity (holiday editor, demo expansion, etc.). The user's philosophy: iron out issues before passing to users, not have users discover bugs.

---

## Test Fixture

**File:** `tests/fixtures/npde_playwright_test_fixture.json`

Copy of `npde_demo.json` with dates modified to ensure both past and future tasks:

- **TASK-001** (Program kickoff): 2025-06-02, complete
- **TASK-002** (Mask design): 2025-06-03 → 2025-06-16, complete
- **TASK-003** (Wafer fab): 2025-06-17 → 2025-07-07, **incomplete** (overdue — triggers auto-catchup)
- **TASK-011** (Local Assembly): 2025-07-08 → 2025-07-10, complete
- **TASK-014** (Filler task): 2025-07-08 → **2026-09-18**, e_days, 438-day cycle — bridges the gap
- **TASK-004** (Assembly): depends on Filler task → starts ~2026-09-20 (future)
- **TASK-005 through TASK-013**: chain from Assembly → all future dates

This gives: ~half tasks in the past, ~half in the future, with one overdue incomplete task for auto-catchup testing.

### DATE MAINTENANCE WARNING

> **When we reach August 2026**, the "future" tasks in this fixture will start becoming current/overdue. At that point, push the dates back using a similar method: shift TASK-001's manual_start_date further into the past and recalculate the Filler task's cycle_time_days to bridge to a new future target date. This keeps the test fixture relevant with both past and future tasks. The Filler task's cycle_time_days is the single knob to turn.

---

## Design Decisions

### Q1 — Server lifecycle

**Decision:** Fixture-managed. A pytest session-scoped fixture starts `python -m streamlit run` on a free port, health-checks until responsive, yields the URL, and kills the process on teardown.

**Why:** Self-contained tests are more reliable for both local dev and future CI. No manual server startup step.

### Q2 — Test isolation

**Decision:** Fresh project per test. Each test copies the fixture JSON into `projects/`, loads it, does its work, and cleans up. Tests can run in any order.

**Why:** Independence is worth the small speed cost. A failure in one test doesn't cascade to others. No `pytest-ordering` plugin needed.

### Q3 — Multi-step sequences

**Decision:** Composable helpers (Pattern C). Reusable async functions like `add_task()`, `click_save()`, `click_validate()` encapsulate Playwright interactions. Tests compose them freely.

**Why:** Keeps tests readable and DRY. Each helper is a building block; each test reads as a scenario.

### Q4 — Scope of golden-path flows

**Decision:** All 16 flows in scope — nothing deferred. The rationale is to iron out as much as possible before moving to the next roadmap step.

**Flows covered:**

| # | Flow | Test class |
|---|------|-----------|
| 1 | Load existing project | `TestLoadProject` |
| 2 | Add a task | `TestTaskCRUD` |
| 3 | Edit a task | `TestTaskCRUD` |
| 4 | Delete a task | `TestTaskCRUD` |
| 5 | Delete blocked by dependents | `TestTaskCRUD` |
| 6 | Add a dependency | `TestDependencies` |
| 7 | Remove a dependency | `TestDependencies` |
| 8 | Mark task complete (cascade) | `TestCompletion` |
| 9 | Save + dirty-state indicator | `TestActionButtons` |
| 10 | Validate (clean + errors) | `TestActionButtons` |
| 11 | Build Excel | `TestActionButtons` |
| 12 | Set Baseline | `TestActionButtons` |
| 13 | Auto-catchup (Apply/Undo) | `TestAutoCatchup` |
| 14 | Auto-catchup (Skip) | `TestAutoCatchup` |
| 15 | New project creation | `TestNewProject` |
| 16 | Project switching (Cancel/Discard/Save & Switch) | `TestProjectSwitching` |
| 17 | Manual start date toggle | `TestManualStartToggle` |
| 18 | Settings (auto-delay, snapshots) | `TestSettings` |

### Q5 — Selectors

**Decision:** Key-based selectors (Option B) with text/role matchers as fallback. The app already uses meaningful `key=` parameters on most widgets. Where keys don't surface in the DOM, we fall back to `get_by_role("button", name="Save")` or `locator("text=...")`.

**Why:** No test-only markup in production code. Keys are already there. Text matchers are resilient when button labels are stable.

### Q6 — Assertions

**Decision:** UI + backend + round-trip (Option C). After every persistent operation, verify:
1. UI shows the expected feedback (success toast, dirty indicator change)
2. JSON file on disk contains the expected data
3. Page reload still shows the data correctly

**Why:** The user's philosophy — thorough bug screening before shipping. The backend is tested by 95 pytest tests; Playwright's job is to verify the full round-trip from click to disk to reload.

### Q7 — Browser mode

**Decision:** One headed showcase test (`test_00_showcase_headed`) runs first so the user can visually confirm the harness works. All remaining tests run headless. Set `HEADED=1` env var to force all tests headed for debugging.

**Why:** Headed and headless are functionally identical. The showcase provides visual confirmation upfront; headless is fast for the bulk of the suite.

### Q8 — Timeouts

**Decision:** Tiered. 5-second default for normal interactions, 15-20 seconds for slow operations (Build Excel, server startup, initial page load).

**Why:** Quick feedback when something is broken (5 seconds, not 15). Known-slow operations get patience.

### Q9 — File organization

**Decision:** Two files: `tests/test_streamlit_playwright.py` (test scenarios) + `tests/playwright_helpers.py` (composable helpers). Matches the HANDOFF.md spec.

**Why:** Scales to more test files later (e.g., after holiday editor ships) without restructuring. Helpers module is importable from any future test file.

### Q10 — pytest-playwright

**Decision:** Use the `pytest-playwright` plugin for browser lifecycle management.

**Why:** Eliminates boilerplate, handles cleanup on failure, supports screenshots and traces natively.

### Q11 — Failure diagnostics

**Decision:** Screenshots + Playwright traces on failure. Run with `--tracing retain-on-failure` to capture full interaction timeline.

**Implementation:** Automatic screenshot-on-failure is built into the test harness. Tests using the `page_and_project` fixture get screenshots via a `pytest_runtest_makereport` hook that detects failures and saves a PNG. Standalone tests (Showcase, AutoCatchup, NewProject) use a try/except wrapper that captures screenshots before re-raising. Screenshots are saved to `test-results/screenshots/` (gitignored).

**Why:** Screenshots show what happened. Traces show how it got there — which click didn't register, what the DOM looked like at each step.

### Q12 — Test fixture

**Decision:** Copy of `npde_demo.json` renamed to `npde_playwright_test_fixture.json` with dates shifted to have past (2025) and future (post-9/18/2026) tasks.

**Why:** Realistic multi-location, multi-dependency fixture that mirrors actual usage. More valuable than a minimal synthetic fixture.

### Q13 — Port

**Decision:** Dynamic free port. The fixture asks the OS for an available port via `socket.bind((localhost, 0))`.

**Why:** Eliminates port conflicts when Streamlit is already running for manual testing.

### Q14 — Test ordering

**Decision:** Headed showcase test named `test_00_showcase_headed` so it sorts first alphabetically. No ordering plugin needed.

**Why:** Visual confirmation upfront that the harness works. If it fails, you saw why on screen.

### Q15 — Fixture dates

**Decision:** Half in 2025 (past), filler task bridging to 9/18/2026, remaining tasks in the future. TASK-003 left incomplete and overdue for auto-catchup testing.

**Why:** Ensures tests exercise both completed/overdue and future/scheduled paths regardless of when they run.

### Q16 — Dependencies

**Decision:** Separate `test-ui` optional dependency group in `pyproject.toml`. `pytest.importorskip("playwright")` guards the test file so backend-only contributors aren't blocked.

**Why:** Backend contributors shouldn't need 150 MB of Chromium to run `pytest -q`.

### Q17 — CI integration

**Decision:** Local-only for now. Tests marked with `@pytest.mark.playwright` and excluded from CI via `-m "not playwright"`.

**Why:** Brand-new tests need local stabilization first. Flaky UI tests in CI erode trust in the test suite.

> **MIGRATION NOTE:** Once all roadmap steps are complete (through Step 11), promote Playwright tests to CI. The recommended approach is a separate GitHub Actions job that installs Chromium and runs `pytest -m playwright`. This should be implemented as part of the final stabilization pass, not earlier.

---

## Current Coverage

**23 tests** across **10 test classes**, covering **18 flows**:

| # | Test | Class | Status | Assertion depth |
|---|------|-------|--------|-----------------|
| 1 | `test_00_showcase_headed` | `TestShowcase` | Written | UI + JSON + reload |
| 2 | `test_load_existing_project` | `TestLoadProject` | Written | UI (project ID, task count, clean indicator) |
| 3 | `test_add_task` | `TestTaskCRUD` | Written | UI + JSON |
| 4 | `test_edit_task` | `TestTaskCRUD` | Written | UI + JSON + reload |
| 5 | `test_delete_task` | `TestTaskCRUD` | Written | UI + JSON |
| 6 | `test_delete_task_blocked_by_dependents` | `TestTaskCRUD` | Written | UI (error message) |
| 7 | `test_add_dependency` | `TestDependencies` | Written | UI + JSON |
| 8 | `test_remove_dependency` | `TestDependencies` | Written | UI + JSON |
| 9 | `test_mark_complete_with_cascade` | `TestCompletion` | Written | UI + JSON |
| 10 | `test_validate_clean` | `TestActionButtons` | Written | UI (alert presence) |
| 11 | `test_validate_with_errors` | `TestActionButtons` | Written | UI (alert presence) |
| 12 | `test_save_and_dirty_state` | `TestActionButtons` | Written | UI + JSON |
| 13 | `test_build_excel` | `TestActionButtons` | Written | UI + file on disk |
| 14 | `test_set_baseline` | `TestActionButtons` | Written | UI + JSON |
| 15 | `test_auto_catchup_apply_and_undo` | `TestAutoCatchup` | Written | UI (catchup applied text, undo button) |
| 16 | `test_auto_catchup_skip` | `TestAutoCatchup` | Written | UI (skip button removed) |
| 17 | `test_create_new_project` | `TestNewProject` | Written | UI + file on disk |
| 18 | `test_switch_cancel` | `TestProjectSwitching` | Written | UI (project ID preserved) |
| 19 | `test_switch_discard` | `TestProjectSwitching` | Written | UI (discard button click) |
| 20 | `test_switch_save_and_switch` | `TestProjectSwitching` | Written | UI + JSON |
| 21 | `test_manual_start_toggle` | `TestManualStartToggle` | Written | UI + JSON |
| 22 | `test_auto_delay_toggle` | `TestSettings` | Written | JSON (setting value flipped) |
| 23 | `test_snapshot_count` | `TestSettings` | Written | JSON (setting value set) |

### Known coverage gaps

These flows are **not yet tested** and should be added as the UI evolves:

- **Holiday editor** (Step 8) — not yet implemented.
- **"New Here?" walkthrough** — visual-only; no data mutation, so lower priority.
- **Dependency Explanation expander** — read-only, no side effects.
- **Summary table rendering** — read-only dataframe; would benefit from a visual regression test once `test_excel_visual.py` patterns are established.
- **Browser beforeunload behavior** — the `_pmsuiteAllowReload` JS flag is tested implicitly via Save flows, but not explicitly tested for tab-close scenarios (Playwright can't fully test native browser dialogs).
- **Concurrent editing / race conditions** — single-user tool, out of scope unless multi-user is added.

### Stabilization status

The test suite was written and selectors were fixed after a first run (3/23 passing). The rewritten helpers target Streamlit's actual DOM structure (`<details>/<summary>` for expanders, `data-testid` attributes, `get_by_role`/`get_by_label` for forms). A full green run has not yet been confirmed — the next agent should run the suite, debug any remaining selector or timing failures, and commit once stable.

---

## Running the tests

```bash
# Install UI test dependencies
pip install -e ".[test-ui]"
playwright install chromium

# Run all Playwright tests (headless)
pytest tests/test_streamlit_playwright.py -m playwright -v

# Run the headed showcase only (watch the browser)
HEADED=1 pytest tests/test_streamlit_playwright.py -k test_00

# Run with trace capture for debugging failures
pytest tests/test_streamlit_playwright.py -m playwright --tracing retain-on-failure

# Run backend tests only (skips Playwright)
pytest -m "not playwright"

# Run everything (backend + Playwright)
pytest -v
```

---

## Cross-references

- [HANDOFF.md](HANDOFF.md) — roadmap and current state
- [MASTERECAP.md](MASTERECAP.md) — design decisions the UI implements
- [STREAMLIT.md](STREAMLIT.md) — UI spec
- [API.md](API.md) — Python API the UI calls
