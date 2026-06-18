# PMSuite — JSON-Driven Excel Gantt Chart Builder

A Python tool that generates Excel Gantt chart workbooks from a structured JSON project file. Designed for semiconductor New Product Development & Execution (NPDE) workflows that span multiple global sites with different work-weeks and holidays.

## What it is

- **Source of truth:** structured JSON project files (`projects/*.json`).
- **Output artifact:** timestamped Excel workbooks (`output/gantt_<project_id>_<YYYY-MM-DD>_<HHMMSS>.xlsx`).
- **Editing surface:** local Streamlit UI calling the documented Python API. Manual Excel edits do not sync back to JSON.
- **Audience:** project managers, engineers, and program coordinators across globally distributed semiconductor sites.

## Prerequisites

- **Python 3.11 or newer** (tested on 3.11 and 3.12)
- **Git** for cloning the repo
- **Windows, macOS, or Linux** (developed on Windows 11; no OS-specific dependencies)

## Full setup (new machine)

### 1. Clone the repo

```bash
git clone https://github.com/Frosty-STI/PMSuite.git
cd PMSuite
```

### 2. Create and activate a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

For general use (Streamlit UI + Excel generation):
```bash
pip install -e ".[dev]"
```

This installs: `pydantic`, `xlsxwriter`, `holidays`, `streamlit`, `python-dateutil`, `tzdata`, `pytest`, `openpyxl`.

For Playwright UI tests (optional — requires Chromium):
```bash
pip install -e ".[test-ui]"
playwright install chromium
```

### 4. Verify the installation

```bash
python -m pytest -q --ignore=tests/test_streamlit_playwright.py
```

Expected: **95 passed** in under 2 seconds.

### 5. Launch the Streamlit UI

**Windows (PowerShell):**
```powershell
python -m streamlit run ui\streamlit_app.py --server.headless true
```

**macOS / Linux:**
```bash
python -m streamlit run ui/streamlit_app.py --server.headless true
```

Open http://localhost:8501 in your browser. The `--server.headless true` flag skips the email prompt on first launch.

If `streamlit` is on your PATH, you can also use `streamlit run ui/streamlit_app.py` directly.

### 6. Explore a demo project

In the sidebar dropdown, select `examples/npde_demo.json`. This is a 17-task multi-location NPDE demo with parent/child hierarchy, 5 global sites, and 173 real holidays. Click **Build Excel** to generate a workbook in `output/`.

## Directory layout

```
PMSuite/
├── gantt_builder/          # Python package (scheduling, validation, Excel generation)
├── ui/streamlit_app.py     # Streamlit editing surface
├── tests/                  # 95 backend tests + 25 Playwright UI tests
├── examples/               # Demo projects (committed to git)
│   ├── small_demo.json     # 7 tasks, DAL only, 27 US holidays
│   └── npde_demo.json      # 17 tasks, 5 locations, parent/child hierarchy, 173 holidays
├── projects/               # YOUR project files (gitignored, local only)
│   └── .backups/           # Rotating snapshots for crash recovery
├── output/                 # Generated Excel workbooks (gitignored)
├── DESIGN.md               # Architecture and scheduling rules
├── MASTERECAP.md           # All 35 design decisions with rationale
├── API.md                  # Python API contract
├── JSONFILE.md             # JSON schema reference
├── EXCELBUILDER.md         # Excel output spec (5 sheets, colors, layout)
├── STREAMLIT.md            # UI spec
├── HANDOFF.md              # Resume-from-here for agents/developers
├── EXECUTIVE_CHANGES_SUMMARY.md  # Detailed changelog for every push
├── PLAYWRIGHT_SCREENING.md # Playwright test design decisions
└── pyproject.toml          # Package metadata and dependencies
```

## Your data is local

**Your project JSON files live on YOUR machine and are NEVER pushed to GitHub.** The `projects/` directory is gitignored. Rotating local snapshots are kept in `projects/.backups/` for crash recovery (last 10 by default, configurable per project).

Back up `projects/` to your own cloud / network share / external drive for versioned history.

## How it works

```
JSON project file  →  Python loader/validator
                  →  Scheduling engine (calendar math, dependency cascade, delay propagation)
                  →  Excel builder (xlsxwriter)
                  →  5-sheet workbook: Chart Key, Day View, Week View, Schedule Calculations, Critical Path Notes
```

The scheduler resolves per-task calendar modes (working days vs e-days), per-task completion locations (DAL, MLA, CLARK, TAI, TIPI, TIEMA, FR-BIP, AIZU), holiday partitioning, parent/subtask rollups with collapsible Excel row grouping, parent-aware scheduling floors, and rich FS/SS/FF/SF dependencies with predecessor-calendar lag.

## Running tests

```bash
# Backend tests only (fast, ~1 second)
python -m pytest -q --ignore=tests/test_streamlit_playwright.py

# Playwright UI tests (requires Chromium, ~4 minutes)
python -m pytest tests/test_streamlit_playwright.py -m playwright

# Everything
python -m pytest -v
```

## Key documentation

| Document | Purpose |
|----------|---------|
| [HANDOFF.md](HANDOFF.md) | Current state, commit table, roadmap, resume instructions |
| [DESIGN.md](DESIGN.md) | Architecture, scheduling rules, data model |
| [MASTERECAP.md](MASTERECAP.md) | All 35 design decisions with rationale |
| [API.md](API.md) | Python API contract and exception hierarchy |
| [JSONFILE.md](JSONFILE.md) | JSON schema reference with examples |
| [EXCELBUILDER.md](EXCELBUILDER.md) | Excel output spec (sheets, colors, layout) |
| [EXECUTIVE_CHANGES_SUMMARY.md](EXECUTIVE_CHANGES_SUMMARY.md) | Detailed changelog for every push |

## Troubleshooting

**`streamlit` not found:** Use `python -m streamlit run ...` instead. The `streamlit.exe` may not be on your PATH.

**Email prompt on first Streamlit launch:** Pass `--server.headless true` to skip it, or press Enter to dismiss.

**PowerShell shows red text on pip install / Streamlit launch:** PowerShell prints stderr in red even for non-errors. Check the actual content — pip warnings and Streamlit logging are harmless.

**Tests fail on import:** Make sure you installed with `pip install -e ".[dev]"` (the `-e` editable flag and `[dev]` extras are both required).

## License

MIT.
