# PE Suite — Design

PE Suite is a local Windows desktop suite for product engineers. It is the place a
product engineer opens to see everything they need: schedules, tasks, priorities,
updates, and material tracking. It is built to be **expanded over time** without the
structure falling apart.

This document is the durable reference for the architecture. Decisions here were made
deliberately; change them deliberately.

---

## 1. The five panes, three categories

| Category | Pane | Data source |
|---|---|---|
| Foundation | **Gantt chart** | selected project's JSON (via PMSuite engine) |
| Derived | **Tasks** | selected project's JSON |
| Derived | **Priorities** | selected project's critical path |
| Fetched | **Updates** | external sources, cached |
| Fetched | **Material Tracking** | external sources, cached |

The **global project selector** lives in the app top bar (not inside any pane) and
drives Gantt + Tasks + Priorities together. Updates has its own project + source
filters. Material Tracking is a **project picker** in the right column (Priorities on
top, Material picker below): it shows one box per project, and clicking a box launches
that project's Material Tracking in **its own window**. Any pane can also be maximized to
fill the window via its header button. No fabricated data — fetched panes are empty until
a real source is registered.

---

## 2. Five layers, clean boundaries

Every piece of code belongs to exactly one layer. A new feature touches one layer, not
the whole app. This is what keeps the suite expandable.

| Layer | Owns | Source of truth |
|---|---|---|
| **Project data** | `project/settings/tasks` JSON + scheduling/critical-path math | PMSuite engine + `projects/` |
| **Fetched data** | scraped/cached external records | hidden SQLite store |
| **Derived views** | Tasks list, Priorities, native Gantt geometry | pure functions over Project data |
| **UI state** | selected project, pane filters, window layout | in-memory app state |
| **Source integrations** | one plugin per external source | isolated behind the `Source` contract |

Two rules enforce the boundaries:

1. **Derived views never fetch.** They are pure functions of project data.
2. **Fetchers never touch the UI.** They run out-of-process and write to a store.

The two data worlds (project vs fetched) only meet at the pane level.

---

## 3. Repository layout (monorepo)

```
pe-suite/                     # repo root: C:\Users\bridg\Projects\pe-suite
├── pmsuite/                  # the existing PMSuite app, vendored in
│   ├── gantt_builder/        # ENGINE: schema + scheduling + critical path (UI-free)
│   ├── ui/streamlit_app.py   # the editor, launched as a subprocess
│   └── projects/             # SOURCE-OF-TRUTH project JSON (shared: PE Suite + editor)
├── pesuite/
│   ├── core/                 # project discovery, loading, derived views
│   │                         #   imports gantt_builder — never reimplements it
│   ├── app/                  # PySide6 shell, global selector, editor_launcher
│   ├── panes/                # gantt, tasks, priorities, updates (+ material window)
│   └── fetch_client/         # thin read-only API over the SQLite store (later)
├── fetch_service/            # SEPARATE process: Playwright + plugins -> SQLite (later)
└── scripts/                  # verification / dev tooling
```

**The engine is shared, not copied.** PE Suite imports `gantt_builder`. The Streamlit
editor and PE Suite compute dates and critical path from the *same* code, so they can
never disagree.

---

## 4. Decisions (locked)

- **Shell:** PySide6/Qt + QWebEngine. (tkinter rejected — must feel modern and smooth.)
- **Engine:** reuse PMSuite's `gantt_builder` (scheduling + critical path). Confirmed
  Streamlit-free and importable.
- **Gantt:** rendered natively, read-only, from the JSON. "Launch Editor" spawns
  Streamlit and opens it in the system browser, pointed at the selected project.
- **Priorities:** derived from the **critical path / long pole** (there is no priorities
  field in the schema). Ranked, incomplete, actionable tasks.
- **Projects:** JSON lives in `pmsuite/projects/` — the SAME folder the Streamlit editor
  reads/writes. The global selector enumerates that folder; file-watch + auto-reload keeps
  panes current. Launch Editor opens `?project=projects/<file>`, which the editor resolves
  against that same folder.
- **Fetched data:** a separate fetch-service process runs Playwright + source plugins and
  writes to a hidden SQLite store (+ raw snapshot blobs) under `%LOCALAPPDATA%\PESuite`.
  Never shown to users, never placed in `projects/`. The UI reads the store only.
- **Refresh:** view-driven, cache-first. Render instantly from cache; refresh the viewed
  source (and its related group) in the background; force-refresh available. No constant
  polling.
- **Material Tracking:** a project-picker pane (below Priorities) showing one box per
  project; clicking a box opens that project's Material Tracking in its own window, which
  reads the store. No fabricated data — empty until a real source is registered.
- **Auth (scraped sources):** start with interactive login via a persistent Playwright
  browser context (saved storage state under `%LOCALAPPDATA%\PESuite`); user logs in once,
  the session persists. No credentials stored by us. Later: env-var credentials behind the
  same `requires_auth` flag, no pane or plugin-shape changes.

---

## 5. The fetching framework (built to grow)

A **source** is a self-contained plugin. Adding one is adding a file — it does not touch
the panes or the rest of the app.

```python
class Source(Protocol):              # fetch_service/source.py
    id: str                          # "vendor_x_portal"
    name: str
    group: str                       # sources that refresh together ("material", "updates")
    requires_auth: bool
    refresh_after: timedelta         # per-source staleness window

    def fetch(self, ctx: FetchContext) -> RawSnapshot:
        """Do I/O (urllib / Playwright sync API via ctx). Returns raw bytes, stored verbatim."""

    def parse(self, raw: RawSnapshot) -> list[Record]:
        """Pure HTML/JSON -> normalized records. No I/O; re-runnable on cached raw."""
```

`fetch()` is **synchronous** — Playwright ships a sync API, so even browser-driven
sources need no async plumbing. The pipeline runs in a separate process
(`fetch_service.runner`), writes to the hidden SQLite store (`fetch_service/store.py`),
and the UI reads it through `pesuite.fetch_client.FetchClient` (cache-first reads +
out-of-process refresh). Sources live in `fetch_service/sources/` (demo, HTTP, and a
Playwright scaffold with persistent-context login).

Why this survives heavy future expansion:

- **fetch / parse split** — when a site changes layout, fix `parse()` and replay it
  against stored raw snapshots. No re-scraping, no lost history.
- **normalized `Record`** — Updates and Material Tracking both consume one record type
  tagged with `source` + `project`. Filtering and diffing are uniform regardless of how
  many sources exist.
- **diffs feed Updates for free** — comparing new vs prior records per source *is* the
  "what changed" stream.
- **`group` + plugin registry** — view-driven refresh: open Material Tracking and only the
  `material` group refreshes; everything else stays cold.
- **separate process** — a hung or crashing scrape cannot freeze the Qt UI, and fetching
  keeps working across UI restarts.

---

## 6. Implementation path

Each phase is independently usable. Phases 1–4 deliver the whole project/derived half
before any scraping risk enters.

1. **Engine read layer** — `pesuite.core` loads a project and produces derived views
   (Tasks tree, Priorities). Proven against both demo JSONs. ← current
2. **Shell + global selector** — PySide6 window, five panes, top-bar selector enumerating
   `projects/`, file-watch.
3. **Derived panes** — native Gantt, Tasks tree, Priorities. A complete, useful app.
4. **Launch Editor** — spawn Streamlit subprocess -> system browser at the selected project.
5. **Fetch service skeleton** — separate process, SQLite store, `Source` contract, one
   trivial source end-to-end.
6. **Updates pane** — project + source filters, cache-first reads, diff stream.
7. **Material Tracking** — project-picker pane (boxes) below Priorities that launches a
   per-project Material Tracking window; view-driven group refresh; real sources only
   (first Playwright source uses interactive login). Every pane is also maximizable.

> For day-to-day "how do I add X" instructions, see **ARCHITECTURE.md** (the live
> contributor guide) — it supersedes this section once you're building.
