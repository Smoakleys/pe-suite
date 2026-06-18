# STREAMLIT — UI Spec

The Streamlit UI is a local-only thin client over the [Python API](API.md). The JSON file is the source of truth; the UI is a more pleasant interface for editing than hand-writing JSON.

For the design rationale behind these UX choices, see [DESIGN.md §17](DESIGN.md). For the decision log, [MASTERECAP.md §Q17](MASTERECAP.md#q17--critical-path) and following.

## Launch

```powershell
python -m streamlit run "C:\Users\Frosty\PMsuite\ui\streamlit_app.py"
```

The `streamlit.exe` binary is installed under `C:\Users\Frosty\AppData\Roaming\Python\Python312\Scripts\` but isn't on PATH by default. The `python -m streamlit` form avoids the PATH issue. Once running, the browser opens to `http://localhost:8501`.

### Configuration

A `.streamlit/config.toml` (optional) can hold:

```toml
[server]
headless = true
port = 8501

[browser]
gatherUsageStats = false
```

This is sufficient for local-only operation. No additional config is required for the walking skeleton.

## Layout

### Sidebar (left rail)

- **Project picker dropdown.** Scans `projects/*.json` and `examples/*.json`, displays a unified list with prefixes. Pick to load.
- **New Project button** (planned). Opens a form modal: name, project ID auto-slugged, timezone, output directory, snapshot retention. On submit, writes a minimal valid project to `projects/<slug>.json` and switches to it.
- **Holidays page link** (planned). Navigates to the holiday editor (tabbed by location).
- **Settings panel** (planned). `auto_delay_on_load` toggle, `keep_local_snapshots` slider, output directory text input.

### Main area

- **Header.** Shows the active project's ID and name, plus a small dirty-state badge when there are unsaved changes.
- **Task table.** All tasks, sortable, with: TASK ID, Name, Location, Calendar Mode, Cycle Time, Manual Start, Parent, Dependencies, Complete, Delay Days. Walking skeleton renders this as read-only; full version is in-place editable.
- **Action buttons** in three columns at the bottom: Validate, Save, Build Excel.

## States

### Initial state (no project loaded)

A short instruction: "Pick a project from the sidebar, or load an example to explore." Sidebar guides the user to either a real project (`projects/`) or a demo (`examples/`).

### Project loaded, clean

Task table populated; action buttons enabled. No dirty-state badge.

### Project loaded, dirty (unsaved changes)

- **● Unsaved changes** badge appears in the header.
- Browser `beforeunload` handler is wired so closing the tab/window or refreshing triggers the browser's native "Changes you made may not be saved" dialog. Implemented via a small `<script>` injected through `st.components.v1.html`.

### Project loaded, validation errors

Inline error/warning panel below the action buttons. Each error rendered with its `error_code` and `message`; affected task IDs listed below. Save still works (we don't block save on logical errors per Q13); Build is blocked.

### Project loaded, auto-catchup pending (planned)

When `settings.auto_delay_on_load: true` and missed days exist since `settings.last_auto_delay_run`:

1. **Modal on load:** "X days have passed since the last delay check. Apply auto-catchup now? [Apply] [Skip for now] [Settings]"
2. **If Apply:** dismissible banner reports counts; "View details" expander shows per-task table; affected rows tinted orange until next save; one-click **Undo this batch** available within session.
3. **If Skip:** no changes, banner reminds the user that catch-up is pending.

## Action buttons

### Validate

Runs `api.validate_project(project)`. Calls `with st.spinner("Validating..."):` for the duration.

- On success with no warnings: `st.success("Project is valid.")`
- On success with warnings: `st.warning(...)` for each.
- On `ValidationFailure`: `st.error(...)` for each error, with `error_code: message` format.

### Save

Calls `api.save_project(project, path)`. Atomic write + optional rotating snapshot.

- On success: `st.success(f"Saved to {path}")`. Dirty-state badge clears.
- On error: `st.error(f"Save failed: {exc.message}")`.

**Save always writes** if the project is structurally valid (per Q13 two-tier collect). Logical errors don't block save — they appear as inline warnings.

### Build Excel

Calls `api.build_excel(project)`. Validates first; raises `ValidationFailure` if logical errors are present.

- On success: `st.success(f"Built: {output_path}")`.
- On validation failure: error panel listing each issue.
- On other errors: `st.error(f"Build failed: {exc.message}")`.

Spinner: `with st.spinner("Building Excel..."):`.

## Planned features (not in walking skeleton)

### Task editing in-place

The task table becomes editable: click a cell, edit, the project's in-memory state mutates, dirty-state badge appears, validation reruns inline. Specific editors per column type:

- Text input for Name.
- Dropdown for Location, Calendar Mode.
- Number input for Cycle Time, Delay Days.
- Date picker for Manual Start, Actual Completion.
- Checkbox for Is Complete.
- Multi-select with autocomplete for Dependencies — shows `TASK-XXX — Name`.
- Dropdown (other task IDs) for Parent.

### Add Task button

Adds a new row with auto-generated `TASK-NNN` from `settings.next_task_id`. Row enters edit mode immediately. Increments `next_task_id` on save.

### Delete Task button

Per-row delete. Blocks if other tasks depend on this one — surfaces the affected task IDs and asks the user to remove dependencies first.

### Dependency Explanation expander

A collapsible block above the task table titled **"Understanding Dependencies (FS / SS / FF / SF)"** with plain-language explanations:

- **FS** (Finish-to-Start, default): "The successor starts after the predecessor finishes. Use this for sequential work."
- **SS** (Start-to-Start): "The successor starts when the predecessor starts. Use this for parallel work that must begin together."
- **FF** (Finish-to-Finish): "The successor finishes when the predecessor finishes. Use this for work that must complete in sync."
- **SF** (Start-to-Finish): "The successor finishes when the predecessor starts. Rare but useful for shift-handoff patterns."

Plus a note on lag: "Positive lag delays the successor by N days. Negative lag (lead) lets the successor begin before the predecessor's anchor event."

### Holiday editor page

Dedicated route: **Holidays** in the sidebar. Tabbed view, one tab per location active in the project. Each tab:

- Table of `{date, name, source}` rows. Sortable by date.
- "Add holiday" button → date picker + name text input → adds with `source: "user-added"`.
- Edit / delete per row.
- **Re-seed from library** button. Pulls fresh holidays from the Python `holidays` library and shows a diff: additions, removals, changes. User picks which to accept. No silent overwrites; original `source: "user-added"` entries are never replaced without explicit confirmation.
- Year range filter (default: project span ± 1 year).

Changes integrate with dirty-state tracking.

### Settings panel

A sidebar expander or dedicated page exposing:

- `auto_delay_on_load: bool` toggle.
- `keep_local_snapshots: int` slider (0-100).
- `output_directory: str` text input.
- `date_axis_start` / `date_axis_end`: optional date pickers for axis override.

### Project switcher dialog

When switching to a different project while dirty:

```
You have unsaved changes in PROGRAM-A.
What do you want to do?

  [Cancel]   [Discard]   [Save & Switch]
```

Selecting Cancel keeps the current project. Discard drops in-memory edits and loads the new project. Save & Switch calls `save_project` first, then loads.

## State management

Streamlit reruns the entire script on each user interaction. The `Project` instance and dirty flag must persist in `st.session_state`:

```python
if "project" not in st.session_state:
    st.session_state.project = None
    st.session_state.project_path = None
    st.session_state.dirty = False
    st.session_state.last_auto_catchup_result = None
```

Every mutation handler updates `st.session_state.dirty = True`. Save handler sets it back to `False`.

## Single project per session

The UI does not support multiple projects open simultaneously. Users who need to compare two projects open two Streamlit instances on different ports:

```powershell
python -m streamlit run ui\streamlit_app.py --server.port 8502
```

## Browser unload warning

When `st.session_state.dirty == True`, inject:

```python
st.components.v1.html("""
<script>
window.onbeforeunload = function() {
    return "You have unsaved changes that will be lost.";
};
</script>
""", height=0)
```

When the user saves, set `window.onbeforeunload = null` via the same component. Modern browsers ignore the custom message and show their own ("Changes you made may not be saved") — that's fine; the goal is just to trigger the warning.

## Streamlit version requirements

- `streamlit >= 1.30` (for stable `st.dataframe` editing, `st.components.v1.html`, modal-style forms via `st.form`).
- Browser: any current Chrome / Edge / Firefox / Safari.

## Current UI state after Step 5

What works today:

- Project picker dropdown (projects/ + examples/).
- Project loading and display.
- Read-only task table.
- Validate / Save / Build Excel buttons with spinners and error rendering.

What's still pending for Step 6:

- Everything labeled "(planned)" above. Specifically:
  - Task editing (add, edit, delete in-place).
  - Dependency picker with autocomplete.
  - Holiday editor page.
  - New Project button.
  - Settings panel.
  - Auto-catchup modal and banner.
  - Dirty-state badge and browser beforeunload warning.
  - Project switcher dialog.

These land in the Streamlit editing-surface commit (step 6 in the post-grilling implementation plan; see [HANDOFF.md](HANDOFF.md)).
