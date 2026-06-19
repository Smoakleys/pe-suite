# PE Suite — Architecture & Contributor Guide (LIVE DOCUMENT)

> **⚠️ THIS IS A LIVING DOCUMENT. UPDATE IT IN THE SAME COMMIT AS ANY CHANGE.**
>
> If you add a pane, a data source, a config path, a signal on a shared service, or
> change the layout — **edit this file in the same commit.** A change that touches the
> structure but not this doc is incomplete. The "Change checklist" at the bottom tells
> you exactly what to update. Treat a stale `ARCHITECTURE.md` as a broken build.

This document explains how PE Suite is put together and — more importantly — gives you
**dead-simple, copy-pasteable recipes** for the two things we do most often:

1. [Add a new pane / feature](#recipe-1-add-a-new-pane) — UI that shows project data.
2. [Add a new fetched data source](#recipe-2-add-a-new-fetched-source) — Updates / Material.

If you only read one section, read the recipe you need. Everything above it is the
"why" that makes the recipe safe.

---

## 1. The one idea that makes this easy

PE Suite has **five layers with one-directional dependencies**. Code in a layer may
import *downward* but never *upward*. This is the whole reason features and sources drop
in cleanly: a new pane or source plugs into a layer without the other layers noticing.

```
  ┌─────────────────────────────────────────────────────────────┐
  │  pesuite/app, pesuite/panes        UI  (PySide6)             │   imports ↓ only
  ├─────────────────────────────────────────────────────────────┤
  │  pesuite/core            DERIVED VIEWS (pure, dataclasses)   │
  │  pesuite/fetch_client    READ-ONLY window into fetched data  │
  ├─────────────────────────────────────────────────────────────┤
  │  pmsuite/gantt_builder   ENGINE (schedule, critical path)    │
  │  fetch_service           FETCH (Source plugins, SQLite)      │
  └─────────────────────────────────────────────────────────────┘
```

The two hard rules that keep it clean:

- **Derived views never fetch.** `pesuite/core` is pure functions over project JSON.
- **Fetchers never touch the UI.** `fetch_service` has **no Qt and no `pesuite` imports**;
  it runs in its own process and writes a SQLite store the UI only reads.

Because of these rules:

- A **new pane** only needs data that already exists (a `LoadedProject` from `core`, or
  the `FetchClient`). It can't destabilize anything else.
- A **new source** is one file behind the `Source` contract. The panes, the store, and
  the refresh machinery already speak `Record` — they don't change when sources multiply.

---

## 2. Where everything lives

```
pe-suite/
├── pmsuite/                      # vendored engine + Streamlit editor (don't fork logic)
│   ├── gantt_builder/            # ENGINE: schema, scheduler, critical_path
│   ├── ui/streamlit_app.py       # the editor, launched as a subprocess
│   └── projects/                 # SOURCE-OF-TRUTH project JSON (shared with editor)
├── pesuite/
│   ├── config.py                 # all on-disk locations live here (one import surface)
│   ├── core/                     # project discovery + derived views (UI-free, pure)
│   │   ├── projects.py           #   discover_projects(), load_project() -> LoadedProject
│   │   └── views.py              #   task_rows(), priorities() -> plain dataclasses
│   ├── app/                      # the shell
│   │   ├── main.py               #   entry point (self-heals to the venv)
│   │   ├── main_window.py        #   top bar, pane grid, global selector, maximize
│   │   ├── state.py              #   AppState: the selected-project hub (signals)
│   │   ├── theme.py              #   ALL colors + the QSS stylesheet
│   │   ├── editor_launcher.py    #   StreamlitEditor (Launch Editor)
│   │   └── material_window.py    #   per-project Material Tracking window (own window)
│   ├── panes/                    # one file per pane (see Recipe 1)
│   │   ├── base.py               #   Pane card: header, body, maximize button
│   │   ├── gantt_pane.py, gantt_chart.py
│   │   ├── tasks_pane.py, priorities_pane.py
│   │   ├── updates_pane.py       #   the cross-source change feed (own filters)
│   │   └── material_pane.py      #   project picker (boxes) -> launches material_window
│   └── fetch_client/             # FetchClient: cache-first reads + out-of-proc refresh
├── fetch_service/                # the fetch process (NO Qt, NO pesuite imports)
│   ├── source.py                 #   Source contract + SourceRegistry
│   ├── models.py                 #   RawSnapshot, Record, read DTOs
│   ├── store.py                  #   SQLite: records, raw snapshots, diff -> update feed
│   ├── service.py                #   refresh_source / refresh_group pipeline
│   ├── runner.py                 #   CLI entry point (the separate process)
│   ├── paths.py                  #   hidden store + browser-profile locations
│   └── sources/                  #   one file per source (see Recipe 2)
│       └── __init__.py           #   register_all(): the ONE place sources are listed
└── scripts/                      # verify_*.py (run these after any change)
```

---

## 3. How a project flows to the screen (derived side)

```
 global selector (top bar)
      │  path
      ▼
 AppState.open_project(path) ──► core.load_project() ──► LoadedProject
      │  projectChanged(LoadedProject)                    (project + schedule + critical path)
      ▼
 every derived pane's .render(loaded):
      core.task_rows(loaded)   -> Tasks tree
      core.priorities(loaded)  -> Priorities cards
      loaded.schedule          -> Gantt bars
```

`AppState` is the hub. Panes **listen** to `projectChanged`; they never load projects
themselves. The global selector drives **Gantt + Tasks + Priorities**. The Updates pane
has its own filters; the **Material pane is a project picker (boxes)** that launches a
per-project Material Tracking *window* — both driven by the FetchClient, not the global
selector. The project list everywhere comes from the same project JSON the derived panes
use (`discover_projects`).

## 4. How fetched data flows (fetched side)

```
 Updates pane  /  Material Tracking window
      │  refresh_group("updates" | "material", project_id)
      ▼
 FetchClient ──spawns──► python -m fetch_service.runner --group ...   (separate process)
      │  (UI stays responsive)          │
      │                                  ▼
      │                       Source.fetch() -> RawSnapshot (stored verbatim)
      │                       Source.parse() -> [Record]
      │                       Store.upsert_records(): diff -> new/changed/removed feed
      │  refreshed(group, ok)            │
      ▼                                  ▼
 reload()  ◄────────cache-first reads──  hidden SQLite store (%LOCALAPPDATA%\PESuite)
```

**Cache-first:** views render instantly from the store, then refresh the viewed group in
the background and re-read. Nothing scrapes unless it's being looked at or force-refreshed.

**No fabricated data:** the app registers **no demo sources**. On startup `FetchClient`
calls `Store.prune_to_sources(all_known_source_ids())`, so any cached rows whose source no
longer exists are removed — the panes can only ever show data from a real, registered
source.

---

## Recipe 1: Add a new pane

**Goal:** a new card in the window that shows project data. Example: a "Locations" pane.

### Step 1 — create the pane file

`pesuite/panes/locations_pane.py`:

```python
from pesuite.app.state import AppState
from pesuite.core import LoadedProject
from .base import Pane


class LocationsPane(Pane):
    def __init__(self, state: AppState) -> None:
        super().__init__("Locations")          # title shown in the header
        # ... build your widget(s) and call self.set_content(widget) ...
        state.projectChanged.connect(self.render)   # react to the global selector
        self.show_placeholder("No project selected.")

    def render(self, loaded: LoadedProject | None) -> None:
        if loaded is None:
            self.show_placeholder("No project selected.")
            return
        # read ONLY from `loaded` (and pesuite.core helpers) — never fetch, never do I/O
        # ... populate your widget ...
        self.show_content()
```

You get the **maximize button, empty-state handling, and card styling for free** from
`Pane`. If your pane needs header controls (filters/buttons), build a small `QWidget` and
pass it as `header_extra=` to `super().__init__`.

### Step 2 — export it

In `pesuite/panes/__init__.py`, add the import and the `__all__` entry.

### Step 3 — place it in the grid

In `pesuite/app/main_window.py → _build_panes()`:

```python
self.locations_pane = LocationsPane(self.state)
# add it to a splitter, e.g. the right column:
self.right_split.addWidget(self.locations_pane)
# and include it in the maximize wiring loop:
for pane in (..., self.locations_pane):
    pane.maximizeRequested.connect(lambda p=pane: self._toggle_maximize(p))
```

### Step 4 — derive any new data purely

If your pane needs a computed view that doesn't exist yet, add a **pure function** to
`pesuite/core/views.py` that takes a `LoadedProject` and returns a plain dataclass (like
`task_rows` / `priorities`). Do **not** put computation in the pane. Export it from
`pesuite/core/__init__.py`.

### Step 5 — verify & document

```bash
.venv/Scripts/python.exe scripts/verify_shell.py     # wiring still sound
.venv/Scripts/python.exe scripts/verify_gantt.py     # renders a PNG preview to eyeball
```

Then **update this file** (add the pane to §2 and to the layout in `main_window.py`'s
docstring) — same commit.

> That's it. You touched `panes/` and one spot in `main_window.py`. No other layer moved.

---

## Recipe 2: Add a new fetched source

**Goal:** pull data from somewhere external into Updates or Material Tracking. Example:
a supplier portal scraped with Playwright.

### Step 1 — write the source file

`fetch_service/sources/acme_portal.py`:

```python
from datetime import datetime, timedelta, timezone
from ..models import RawSnapshot, Record
from ..source import BaseSource, FetchContext


class AcmePortalSource(BaseSource):
    id = "acme_portal"          # unique, stable
    name = "Acme Supplier Portal"
    group = "material"          # "material" or "updates" — which pane/group it feeds
    requires_auth = True        # uses the persistent browser profile for login
    refresh_after = timedelta(minutes=30)   # staleness window before a re-fetch

    def fetch(self, ctx: FetchContext) -> RawSnapshot:
        # Do the I/O here. For HTTP use urllib (see web_example.py); for a browser use
        # the Playwright persistent-context pattern (see playwright_example.py), which
        # keeps the user logged in across runs via ctx.browser_profile_dir.
        raw_bytes = ...          # the page/JSON you fetched
        return RawSnapshot(content=raw_bytes, content_type="text/html",
                           meta={"url": "https://acme.example/orders"})

    def parse(self, raw: RawSnapshot) -> list[Record]:
        # PURE: no I/O. Turn raw bytes into normalized Records. Because parse is pure,
        # if the site layout changes you fix THIS method and replay it on stored raw
        # snapshots — no re-scraping, no lost history.
        records = []
        for row in ...:          # parse raw.content
            records.append(Record(
                source_id=self.id, group=self.group, kind="po",
                key=row["po_number"],          # STABLE id used for diffing
                title=row["item"], project_id=row["project_id"],
                body=f"{row['status']} · ETA {row['eta']}",
                data={"status": row["status"], "qty": row["qty"],
                      "eta": row["eta"], "supplier": "Acme", "po": row["po_number"]},
            ))
        return records
```

**The `key` is the contract for change detection.** Same `key` + changed content → a
"changed" update; new `key` → "new"; a `key` that disappears → "removed". Pick something
stable (PO number, ticket id, URL).

For Material rows, put structured fields in `data` (`status`, `qty`, `eta`, `supplier`,
`po`) — the Material Tracking window reads those column keys.

> **No fabricated data, ever.** The app ships with **zero demo sources**. Until you
> register a real source, Updates and the Material window are honestly empty. Don't add a
> source that invents data.

### Step 2 — register it (the ONLY wiring step)

In `fetch_service/sources/__init__.py → register_all()`:

```python
def register_all(registry, include_network=False, include_playwright=False):
    # Real sources go here:
    from .acme_portal import AcmePortalSource      # <-- add
    registry.register(AcmePortalSource())          # <-- add

    if include_network:
        from .web_example import ExampleWebSource
        registry.register(ExampleWebSource())
    ...
    return registry
```

That's the whole integration. **No pane changes. No store changes. No UI changes.** The
Updates pane and Material window already iterate `Record`s, so your source appears
automatically. (Removing a source later is just as clean: delete its file + this line, and
its cached rows **self-prune** on next startup via `Store.prune_to_sources`.)

### Step 3 — try it out of process

```bash
# runs the real pipeline against the hidden store and prints a JSON summary
.venv/Scripts/python.exe -m fetch_service.runner --group material --force
# (network/Playwright sources are opt-in)
.venv/Scripts/python.exe -m fetch_service.runner --group updates --network --force
```

### Step 4 — verify & document

```bash
.venv/Scripts/python.exe scripts/verify_fetch.py      # pipeline + diff + runner CLI
.venv/Scripts/python.exe scripts/verify_ui_fetch.py   # panes render fetched data
```

Then **update this file** (note the new source under §2's `sources/` and, if it needed a
new dependency like `playwright`, the README setup) — same commit.

#### Auth note (interactive now, env vars later)

`requires_auth = True` sources use a **persistent Playwright profile** under
`%LOCALAPPDATA%\PESuite\browser_profile` — the user logs in once and the session persists.
No credentials are stored by us. When we move to headless/credentialed login, swap the
login step for env-var credentials **behind the same `requires_auth` flag** — panes and
the `Source` shape do not change.

---

## 5. Shared services & signals (don't break these contracts)

| Service | Where | Contract |
|---|---|---|
| `AppState` | `app/state.py` | `projectChanged(LoadedProject|None)`, `open_project()`, `reload()`. The single source of truth for the selected project. |
| `FetchClient` | `fetch_client/client.py` | reads: `updates()`, `materials()`, `source_names()`; refresh: `refresh_group(group, project_id, force)`; signals: `refreshStarted(group)`, `refreshed(group, ok)`. Self-heals on init: prunes store data from unknown sources. |
| `StreamlitEditor` | `app/editor_launcher.py` | `launch(project_path)` → opens the editor in the browser; managed subprocess. |
| `Pane` | `panes/base.py` | `set_content()`, `show_placeholder()`, `show_content()`, `maximizeRequested`, `set_maximized()`. |
| `config` | `pesuite/config.py` | **all** on-disk paths: `projects_dir()`, `streamlit_script()`, `fetch_store_path()`, `browser_profile_dir()`, `app_data_dir()`. Add new locations here, nowhere else. |

If you add a signal or method to one of these, add a row/contract note here.

## 6. The maximize / full-screen model

Every pane has a maximize button (`Pane.maximizeRequested`). `MainWindow._toggle_maximize`
pops the pane into a top-level window shown maximized and `_restore_pane` puts it back into
its splitter at the same index. Panes do nothing special to support this — if you follow
Recipe 1, your pane is full-screenable automatically.

## 7. Verify scripts (run the relevant ones before every commit)

| Script | Proves |
|---|---|
| `verify_engine.py` | core read layer derives both demo projects |
| `verify_shell.py` | shell wiring: selector, panes, maximize/restore (headless) |
| `verify_gantt.py` | the Gantt paints; writes PNG previews to `scripts/_preview/` |
| `verify_editor.py` | Launch Editor boots Streamlit and targets the project |
| `verify_fetch.py` | fetch pipeline: fetch→parse→store→diff + runner CLI |
| `verify_ui_fetch.py` | Updates + Material panes render fetched data; refresh round-trip |
| `build_demo_program.py` | (re)generates the large demo project via the engine |

---

## ✅ Change checklist (paste into your PR description)

- [ ] Code change made in the **lowest** layer that suffices (didn't reach upward).
- [ ] Derived computation is a **pure function in `core`**, not in a pane.
- [ ] New fetched logic stays in `fetch_service` (no Qt, no `pesuite` imports).
- [ ] New on-disk path added to **`pesuite/config.py`**, not hardcoded.
- [ ] Ran the relevant **`scripts/verify_*.py`** (and eyeballed a PNG if UI changed).
- [ ] **Updated this `ARCHITECTURE.md`** (file map §2, any signal/contract in §5, and the
      relevant recipe if the steps changed) — in this same commit.
- [ ] Updated `README.md` status/setup if a phase or dependency changed.
```
