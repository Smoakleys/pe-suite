# PE Suite

A local desktop suite for product engineers — schedules, tasks, priorities, updates,
and material tracking in one place. Built to be expanded over time.

**Adding a feature or a data source?** Start with **[ARCHITECTURE.md](ARCHITECTURE.md)** —
the live contributor guide with copy-pasteable recipes. It must be updated with every
change. Adding a **web scraper** has its own small-context, step-by-step guide:
**[docs/SCRAPER_PLAYBOOK.md](docs/SCRAPER_PLAYBOOK.md)**. See **[DESIGN.md](DESIGN.md)** for
the original design rationale and phase plan.

## Layout

- `pmsuite/` — vendored PMSuite Gantt engine + Streamlit editor. PE Suite imports its
  `gantt_builder` engine; it does not reimplement scheduling or critical-path math.
  `pmsuite/projects/` is the shared source-of-truth project JSON folder.
- `pesuite/core/` — read layer: project discovery, loading, and derived views (Tasks,
  Priorities). Pure, read-only, UI-free.
- `pesuite/app/`, `pesuite/panes/` — the PySide6 shell and panes.
- `scripts/` — verification and dev tooling.

## Setup

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install ./pmsuite PySide6
```

## Run the app

```bash
# Preferred: module launch with the project venv.
.venv/Scripts/python.exe -m pesuite.app.main
```

Running the file directly also works from any Python — `python pesuite/app/main.py` —
because the entry point adds the repo root to `sys.path` and re-execs through the
project `.venv` if the engine dependencies aren't found on the current interpreter.

## Verify

```bash
.venv/Scripts/python.exe scripts/verify_engine.py   # phase 1: core read layer
.venv/Scripts/python.exe scripts/verify_shell.py    # phase 2: shell wiring (headless)
.venv/Scripts/python.exe scripts/verify_gantt.py    # phase 3: gantt paint + PNG preview
.venv/Scripts/python.exe scripts/verify_editor.py   # phase 4: launch Streamlit + URL
.venv/Scripts/python.exe scripts/verify_fetch.py    # phase 5: fetch pipeline + runner CLI
.venv/Scripts/python.exe scripts/verify_ui_fetch.py # phases 6-7: Updates + Material panes
```

To enable real scraping sources:

```bash
.venv/Scripts/python.exe -m pip install playwright
.venv/Scripts/python.exe -m playwright install chromium
# then run the fetch runner with --network and/or --playwright
.venv/Scripts/python.exe -m fetch_service.runner --group updates --network --force
```

## Status

- [x] **Phase 1** — engine read layer (`pesuite.core`), proven against demo projects.
- [x] **Phase 2** — PySide6 shell: top-bar global selector, four-pane layout, file-watch
      auto-reload, separate Material Tracking window.
- [x] **Phase 3** — native Gantt chart (`GanttChart`): frozen label column + date header,
      day/week/month axis, critical-path bars, parent summary bars, dependency connectors,
      today line, auto-fit, Ctrl+scroll zoom, hover tooltips. Priorities rendered as cards.
- [x] **Phase 4** — Launch Editor: `StreamlitEditor` starts the editor as a managed
      QProcess (non-blocking readiness poll, free-port pick) and opens the system browser
      at `?project=projects/<file>`; server is shut down with the app.
- [x] **Phase 5** — fetch service: hidden SQLite store under `%LOCALAPPDATA%\PESuite`,
      `Source` plugin contract (fetch/parse split), diff-driven update feed, out-of-process
      `runner`, demo + HTTP + Playwright sources. Read via `pesuite.fetch_client`.
- [x] **Phase 6** — Updates pane: independent project/source filters, cache-first cards,
      view-driven + manual refresh, change badges.
- [x] **Phase 7** — Material Tracking window: separate native window, own selector,
      materials table, view-driven group refresh.

All seven phases are functionally complete and verified (52 checks across 6 suites).
The Playwright source is a scaffold; wire real portals against it as needed.
