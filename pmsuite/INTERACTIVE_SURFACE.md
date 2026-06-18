# INTERACTIVE_SURFACE — Visual Gantt Editing Design

This document records every design decision from the grilling session that produced the interactive Gantt editing surface for PMSuite. Each decision is anchored to its question number (Q1–Q38) so future debates can reference an exact source.

For the existing text-based editing surface, see [STREAMLIT.md](STREAMLIT.md). For architecture, [DESIGN.md](DESIGN.md). For the decision log of the core system, [MASTERECAP.md](MASTERECAP.md).

---

## 1. Purpose

An interactive visual Gantt chart inside the Streamlit app that provides **all of the same functionality** as the existing expander-based text/dropdown editing surface, but through direct manipulation of a timeline. Users can drag bars to change dates, resize bars to change durations, draw dependency arrows between tasks, and edit all task properties in a companion sidebar panel.

The interactive Gantt and the text-based editors coexist as two tabs. Users choose their preferred editing mode; both operate on the same in-memory project.

---

## 2. Technology Stack

### Q1 — Visualization type

**Interactive Gantt chart.** A rendered timeline with bars on a time axis, drag interactions, and dependency arrows. Chosen over node graphs, editable grids, or hybrid approaches because it's the natural representation for a Gantt builder and maps directly to the Excel output users already review.

### Q3 — Rendering library

**Frappe Gantt (MIT license).** Purpose-built JavaScript library for interactive Gantt charts. Provides out of the box:

- Drag bar horizontally → change start date
- Drag bar edge → change duration
- Click bar → select task (fires callback)
- Dependency arrows rendered between bars
- View modes (Day, Week, Month)
- Drag-to-connect dependency creation with connector circles (green = start, orange = end)
- `on_dependency_create`, `on_dependency_changed`, `on_dependency_delete` callbacks
- `allow_dependency_creation: true` (default)

Chosen over Plotly (limited drag interactions), custom HTML/JS (unnecessary effort), and ag-Grid (table, not timeline).

### Q8 — Streamlit ↔ Frappe communication

**Bidirectional Streamlit custom component** built as a React wrapper around Frappe Gantt.

- **Python → JS:** Python sends task data (bars, dependencies, colors, dates) to the component via props.
- **JS → Python:** Frappe callbacks (`on_click`, `on_date_change`, `on_progress_change`, `on_dependency_create`, etc.) fire `Streamlit.setComponentValue()` to send event payloads back to Python.
- **Build tooling:** React (via Vite or CRA), one-time Node.js build step, produces a static bundle shipped with the Python package. Used as `from components.gantt import st_gantt`.

---

## 3. Layout

### Q7 — Tab structure

Two tabs at the top of the main area:

- **"Visualized Project Editing"** — Frappe Gantt + right sidebar detail panel
- **"Text Project Editing"** — Current expander-based editors (unchanged)

Both tabs operate on the same `st.session_state.project` object. Changes in one are reflected in the other when switching tabs. Tab names are fixed.

### Q10b — Chart and sidebar split

**70/30 horizontal split.** The Gantt chart takes 70% width on the left; the sidebar detail panel takes 30% on the right. The sidebar is always visible when shown — no layout shift on task select/deselect.

- **No task selected:** Sidebar shows a prompt ("Click a task bar to edit").
- **Task selected:** Sidebar shows the full editor for that task.

### Q38 — Sidebar hide/show toggle

A collapse/expand button on the sidebar's left edge. When hidden, the Gantt expands to 100% width. Toggling it back restores the 70/30 split. For users who want to maximize the chart for scanning or presenting.

### Q28 — Action buttons

**Same button row as the List View, shared across both tabs.** Located above the Gantt, below the toolbar:

`[Validate] [Save] [Build Excel] [Set Baseline]`

With captions below each button and the dirty-state indicator ("Unsaved changes" in orange / "All changes saved" in green) on the same row. Identical behavior and layout to the List View.

---

## 4. Toolbar

### Q19 — Toolbar contents

A horizontal bar above the Gantt chart containing (left to right):

1. **[+ Add Task]** button — opens the sidebar in "create mode" with empty fields.
2. **View mode switcher** — Day / Week / Month toggle buttons.
3. **[Today]** button — scrolls the chart horizontally to center today's date on screen.
4. **Search box** — highlights matching tasks (see §6 below).
5. **Hint text** (right-aligned, dull white italics) — *"Double click chart to add task at cursor location"*

### Q19b — Double-click to add task

Double-clicking an empty area on the Gantt timeline opens the sidebar in "create mode" with the `manual_start_date` pre-filled from the clicked date position. Same form as the toolbar button, just with a pre-filled date.

---

## 5. Bar Interactions

### Q5 — Drag bar start (horizontal move)

Updates `manual_start_date`. The scheduler resolves `effective_start = max(manual_start_date, dependency-driven start, parent floor)` as usual. If the resolved date differs from where the user dragged, the bar snaps to the corrected position.

### Q5b — Drag bar end (resize duration)

Updates `cycle_time_days` with calendar-mode-aware math:

- **E-day tasks:** count calendar days between start and new end.
- **Working-day tasks:** count only work days (per the task's location work-week and holidays) between start and new end.

Parent tasks block this interaction — their duration is derived from children.

### Q12 — Dependency management

**Sidebar-driven.** Dependencies are created and removed via the sidebar detail panel's dependency section (predecessor dropdown, type selector FS/SS/FF/SF, lag input). Existing dependency arrows are rendered read-only on the chart for visualization.

**Drag-to-connect descoped:** The original design called for Frappe Gantt's native drag-to-connect, but base `frappe-gantt` v1.2.2 does not expose `on_dependency_create` callbacks (that feature existed only in `@workiom/frappe-gantt` which has a fatal ES module bug). The sidebar workflow is fully functional and sufficient — drag-to-connect may be revisited in a future version if a compatible library emerges.

### Q9 — Update speed (optimistic then correct)

After a drag or dependency action, the bar moves/appears immediately (optimistic). Python validates and re-schedules. If the resolved position differs, the bar snaps to the corrected position. Target round-trip: **50–150ms** for typical projects (50–300 tasks).

Optimizations:
- **Partial re-scheduling:** Only re-derive the dragged task and its downstream dependents, not the whole project.
- **Pre-computed dependency graph:** On project load, build a lookup of downstream dependents per task.
- **Warm Python process:** Project object already in memory (Streamlit session state).
- **Debounced drags:** Frappe fires callbacks on drag-end, not during drag.

### Q30 — Sidebar edits vs drag edits

- **Drag interactions** (move bar, resize bar, draw/delete arrow) fire immediately — no Apply button.
- **Sidebar field edits** (name, location, calendar mode, cycle time, etc.) require clicking "Apply changes" — same as the List View. Avoids flicker from intermediate states while typing.

---

## 6. Search and Filter

### Q22 — Search behavior

**Highlight + dim + auto-scroll.** Typing in the search box:

1. Dims non-matching bars to ~30% opacity.
2. Keeps matching bars at full color.
3. Auto-scrolls to the first matching bar.
4. Chart layout doesn't change (no bars hidden or repositioned).
5. Clearing the search restores all bars to full opacity.

### Q22b — Search fields

Matches against **Task ID**, **Task Name**, and **Completion Location**. Case-insensitive partial match.

### Q22c — Placeholder text

The search box shows contextual placeholder text in dull gray, pulled from the actual project data. Example:

> *Search by ID, name, or location (e.g., "TASK-005", "Wafer fab", "TAI")*

Clears on click, reappears when empty and unfocused.

---

## 7. Visual Styling

### Q16 — Bar color palette

**Matches the Excel palette exactly** (MASTERECAP Q26a):

| Status | Color | Hex |
|--------|-------|-----|
| Planned (incomplete) | Pale blue | `#8FB6E1` |
| Completed | Green | `#2E8B57` |
| Delay extension | Orange | `#E68A00` |
| Overdue | Red | `#D9534F` |
| Critical path indicator | Dark red border | `#8B0000` |
| Parent summary bar | Dark gray | `#555555` |
| Today column | Pale yellow | `#FFF8C4` |
| Weekend | Light gray | `#F0F0F0` |
| Holiday | Darker gray | `#B0B0B0` |

### Q18 — Today indicator

Styled today line (vertical stripe matching pale yellow `#FFF8C4` with a dark vertical rule) plus a **[Today]** button in the toolbar that scrolls the chart to center today on screen.

### Q18b — Weekend and holiday markers

- **Weekends:** Vertical light gray stripes on weekend columns.
- **Holidays:** Darker gray stripes with holiday name in tooltip on hover.
- **Location-specific:** When a task is selected, weekend/holiday shading reflects that task's location work-week (Mon–Fri vs Sun–Thu) and location-specific holidays. When no task is selected, defaults to DAL's work-week.

### Q36 — Hover tooltip

Hovering over a bar shows a tooltip with:

- Task ID
- Task Name
- Start date
- End date
- Location
- Status (e.g., "On track", "Overdue by 3 days", "Complete")

Uses Frappe Gantt's native tooltip support, customized with PMSuite data.

---

## 8. Hierarchy

### Q14 — Parent/child display

**Indented bars with collapsible groups.** Mirrors the Excel output:

- Parent tasks render as summary bars (dark gray `#555555`, same as Excel).
- Child bars are indented below the parent.
- A collapse/expand toggle on the parent row hides/shows children — same UX as Excel's `+`/`-` row grouping.
- Supports unlimited depth. Grandchildren indent further.

---

## 9. Task Selection and Context Menu

### Q32 — Selection model

**Single select.** Clicking a bar selects it (highlighted outline) and opens the sidebar detail panel. Clicking another bar switches. Clicking empty space deselects. Multi-select is a future enhancement.

### Q26 — Right-click context menu

Right-clicking a bar shows a four-item menu:

1. **Edit in sidebar** — opens/scrolls the sidebar to this task's editor.
2. **Mark complete / Mark incomplete** — toggles based on current state. Calls `mark_task_complete` / `unmark_task_complete`.
3. **Add child task** — creates a child task pre-filled with parent's location and calendar mode (same as "Add Child Task" button in List View).
4. **Delete task** — blocks with error toast if dependents or children exist.

Undo functionality from the List View is preserved for completion cascade and auto-catchup operations.

---

## 10. Sidebar Detail Panel

### Q10 — Panel contents

The sidebar contains **all fields from the List View expander editors:**

- Task ID (read-only, copy-able)
- Name (text input)
- Location (dropdown)
- Calendar Mode (dropdown)
- Cycle Time in Days (number input; disabled for parents, caption "Derived from children")
- Has Manual Start Date (checkbox toggle) + Date picker
- Delay Days (number input)
- Parent picker (dropdown, filtered to prevent cycles)
- Is Complete (checkbox, fires immediately — same as List View)
- Actual Completion Date (date input, shown when complete)
- Dependencies list (current predecessors with type, lag, and remove button)
- Add dependency form (predecessor dropdown, type selector, lag input)
- Apply changes button (primary)
- Add child task button
- Delete task button

Layout is single-column (sidebar is narrower than the main area) with dividers between sections.

---

## 11. Error Handling

### Q5c — Error message format

Errors from Gantt interactions appear as a **dismissible toast banner above the chart.** Format:

```
Error — Short Label  ❓
```

- **Short label:** 2-4 words summarizing the error (e.g., "Circular Dependency", "Parent Has Cycle Time", "Deletion Blocked").
- **Red circled ❓:** Small, inline in the message. Clicking it expands the banner downward to show:
  - A detailed explanation of what went wrong.
  - An example using the specific tasks involved (e.g., "TASK-005 depends on TASK-008, which depends on TASK-003, which depends on TASK-005 — forming a loop. Remove one of these dependencies to break the cycle.").
- **Auto-dismiss:** After 8 seconds if not interacted with. Stays open if the user clicked ❓.
- **Errors from sidebar edits** also use this toast format (above the Gantt, not inside the sidebar).

---

## 12. Scrolling and Viewport

### Q34 — Vertical scrolling

**Independent scroll with sticky header.** The Gantt chart has its own vertical scrollbar. The date header row (time axis) stays pinned at the top of the chart area as the user scrolls through tasks. The toolbar and action buttons above the chart stay fixed. The sidebar scrolls independently.

Mirrors Excel frozen-pane behavior that users already know from the generated workbooks.

### Q20 — View modes

Three zoom levels via toolbar toggle:

- **Day** — one column per day (matches Excel Day View).
- **Week** — one column per week (matches Excel Week View).
- **Month** — one column per month (new — not available in Excel; useful for scanning 6–12 month NPDE programs).

---

## 13. Responsive Behavior

**Desktop-only.** No responsive breakpoints. The app uses `layout="wide"` and assumes a full-screen browser. Users are expected to view in full screen. The hide/show sidebar toggle (§3, Q38) provides the only layout flexibility needed.

---

## 14. Scope Boundaries (what this feature does NOT include)

- **Multi-select / bulk edit** — future enhancement. Single select only for v1.
- **Drag-to-reorder tasks vertically** — task order is driven by hierarchy and schedule, not manual arrangement.
- **Inline text editing on bars** — all text editing happens in the sidebar.
- **Undo for drag operations** — the bar snaps to the corrected position via the scheduler. To revert a drag, the user changes the value back in the sidebar. (Auto-catchup undo and completion undo are preserved from the List View.)
- **Print / export the Gantt view** — the Excel workbook remains the export artifact.
- **Animation / transitions** — bars snap to resolved positions. No animated sliding.

---

## Cross-references

- [DESIGN.md](DESIGN.md) — architecture-level rationale, scheduling rules.
- [MASTERECAP.md](MASTERECAP.md) — all core design decisions (Q1–Q35).
- [STREAMLIT.md](STREAMLIT.md) — existing text-based UI spec.
- [EXCELBUILDER.md](EXCELBUILDER.md) — Excel output spec (color palette source of truth).
- [API.md](API.md) — Python API contract consumed by both editing surfaces.
- [HANDOFF.md](HANDOFF.md) — resume-from-here document.
