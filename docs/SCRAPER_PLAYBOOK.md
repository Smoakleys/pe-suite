# Scraper Playbook — add a web-scraping source

**Audience:** an agent doing ONE focused job with little context. Read only this file.
You do **not** need to understand PE Suite, Qt, databases, or the fetch service. This
document is self-contained. Follow it top to bottom.

---

## Your job (the whole thing)

Write **one** standalone Python script that scrapes a website and **prints a JSON array
of records to stdout**. Then add **one line** to register it. That's it.

You will NOT:
- touch the database, the UI, Qt, or any pane,
- import anything from the app,
- invent or hardcode fake data (if the site gives nothing, print `[]`).

A wrapper called `ScriptSource` already exists. It runs your script as a subprocess,
reads the JSON you print, and feeds it into the app. You only write the script.

```
  your_script.py  ──prints JSON──►  ScriptSource (already built)  ──►  the app
```

---

## The OUTPUT CONTRACT (this is the only thing that matters)

Your script prints to **stdout** a JSON array. Each element is one record:

```json
[
  {
    "key":        "PO-1001",
    "title":      "Wafer lot WFR-2207",
    "project_id": "DEMO-NPDE",
    "kind":       "po",
    "body":       "In transit, ETA 2026-07-01",
    "url":        "https://supplier.example/orders/1001",
    "timestamp":  "2026-06-18T10:00:00+00:00",
    "data":       {"status": "In Transit", "qty": 25, "eta": "2026-07-01",
                   "supplier": "TAI Fab", "po": "PO-1001"}
  }
]
```

| Field | Required? | Meaning |
|---|---|---|
| `key` | **YES** | A stable, unique id for this item. Same key next run = same item (used to detect changes). Use a PO number, ticket id, or URL. |
| `title` | **YES** | Short human label shown in the app. |
| `project_id` | no | Which project this belongs to (e.g. `"DEMO-NPDE"`). Omit/`null` = global. |
| `kind` | no | Subtype within the group, e.g. `"po"`, `"lot"`, `"announcement"`. |
| `body` | no | Longer text. |
| `url` | no | A link. |
| `timestamp` | no | ISO‑8601 event time, e.g. `"2026-06-18T10:00:00+00:00"`. |
| `data` | no | Any extra fields. **For material rows include:** `status`, `qty`, `eta`, `supplier`, `po` (those are the table columns). |

**Rules of stdout/stderr:**
- **stdout** = the JSON array, and nothing else.
- **stderr** = your human logs/progress (`print(..., file=sys.stderr)`). It's captured for
  debugging and never parsed.
- If something fails, write to stderr and exit non‑zero (`sys.exit(1)`). Do **not** print
  partial/garbage JSON.

---

## Step 1 — copy the template

```bash
cp fetch_service/sources/scripts/_template_scraper.py fetch_service/sources/scripts/my_source.py
```

(Pick a clear filename, e.g. `acme_portal.py`.)

## Step 2 — fill in the `scrape()` function

Open your new file and edit only the `scrape(project_id, profile_dir)` function so it
returns a list of dicts following the contract above. Two patterns:

**A. Simple page or JSON API (stdlib, no install):**

```python
from urllib.request import Request, urlopen
import json

def scrape(project_id, profile_dir):
    req = Request("https://supplier.example/orders.json",
                  headers={"User-Agent": "PE-Suite-Scraper/1.0"})
    with urlopen(req, timeout=15) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
    return [
        {"key": r["po"], "title": r["item"], "project_id": project_id, "kind": "po",
         "data": {"status": r["status"], "qty": r["qty"], "eta": r["eta"],
                  "supplier": r["supplier"], "po": r["po"]}}
        for r in rows
    ]
```

See the complete worked example in `fetch_service/sources/scripts/example_com.py`.

**B. Site needs a login or runs JavaScript (Playwright):**

Use the persistent profile at `profile_dir` so the user logs in once and stays logged in:

```python
def scrape(project_id, profile_dir):
    from playwright.sync_api import sync_playwright   # pip install playwright
    rows = []
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=profile_dir or "", headless=False)  # headless=False the FIRST time so the user can log in
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://portal.example/orders", wait_until="domcontentloaded")
        for el in page.query_selector_all(".order-row"):
            rows.append({"key": el.get_attribute("data-po"),
                         "title": el.inner_text().strip(),
                         "project_id": project_id, "kind": "po"})
        ctx.close()
    return rows
```

Your script receives two optional args you may use or ignore:
`--project-id <id>` and `--profile-dir <path>` (the boilerplate in the template already
parses them and hands them to `scrape`).

## Step 3 — test your script ALONE (no app needed)

```bash
python fetch_service/sources/scripts/my_source.py
# or, scoped to a project:
python fetch_service/sources/scripts/my_source.py --project-id DEMO-NPDE
```

You should see a JSON array on stdout. If you can pipe it through `python -m json.tool`
without error, the contract is satisfied. **If this works, your script is done.**

## Step 4 — register it (one line)

Open `fetch_service/sources/__init__.py` and add inside `register_all(...)`:

```python
from .script_source import ScriptSource
from datetime import timedelta
registry.register(ScriptSource(
    id="acme_portal",            # unique id (lowercase, stable)
    name="Acme Supplier Portal", # shown in the app
    group="material",            # "material" or "updates"
    script="my_source.py",       # your file in fetch_service/sources/scripts/
    requires_auth=False,         # True if it logs in via Playwright
    refresh_after=timedelta(minutes=30),
))
```

- `group="material"` → appears in the per-project Material Tracking window.
- `group="updates"` → appears in the Updates feed.

## Step 5 — test it through the framework

```bash
python -m fetch_service.runner --group material --force
```

You should see a JSON summary like
`{"group":"material","results":[{"source":"acme_portal","records":N,"added":N,...}]}`.

Then run the suite:

```bash
.venv/Scripts/python.exe scripts/verify_scraper.py
```

---

## Definition of done (checklist)

- [ ] One new file in `fetch_service/sources/scripts/` whose `scrape()` returns the records.
- [ ] `python fetch_service/sources/scripts/<file>.py` prints a valid JSON array (stdout only).
- [ ] Every record has `key` and `title`; `key` is stable across runs.
- [ ] No fabricated data — if the site yields nothing, it prints `[]`.
- [ ] One `ScriptSource(...)` line added in `fetch_service/sources/__init__.py`.
- [ ] `python -m fetch_service.runner --group <group> --force` reports your records.
- [ ] `scripts/verify_scraper.py` passes.
- [ ] If you added a dependency (e.g. `playwright`), note it in `README.md`.

## If something breaks

| Symptom | Fix |
|---|---|
| Runner says `did not print valid JSON` | You printed logs to stdout. Send logs to **stderr**; print only the JSON array to stdout. |
| Runner says `record #N missing 'key'/'title'` | Add those two fields to every record. |
| `scraper '...' exited 1` | Your script raised. Read the stderr tail in the message; run the script standalone to debug. |
| Material window empty | Check `group="material"` and that records have `project_id` matching the project. |
| Records duplicate each run | Your `key` isn't stable — derive it from a real id, not a timestamp or row index. |

## What you must NOT touch

`fetch_service/store.py`, `fetch_service/service.py`, `fetch_service/runner.py`,
`fetch_service/sources/script_source.py`, anything under `pesuite/`. Those are built and
tested. Your work is exactly one scraper script plus one registration line.
