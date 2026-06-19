"""TEMPLATE scraper — COPY THIS FILE to start a new scraper.

    cp _template_scraper.py my_source.py     (then edit the TODOs)

Your ONLY job: print a JSON array of records to stdout. Nothing else. You do not import
anything from the app, you do not touch the database, the UI, or Qt. If `python my_source.py`
prints valid JSON, you are done with the script.

Read docs/SCRAPER_PLAYBOOK.md for the full walkthrough. Run this file directly to test it:

    python fetch_service/sources/scripts/_template_scraper.py
"""

from __future__ import annotations

import argparse
import json
import sys


def scrape(project_id: str | None, profile_dir: str | None) -> list[dict]:
    """TODO: replace the body with your real scraping.

    Return a list of dicts. Each dict MUST have "key" and "title". Everything else is
    optional. See the OUTPUT CONTRACT in docs/SCRAPER_PLAYBOOK.md.

    Tips:
      - For a simple page/API: use urllib.request (stdlib) — see example_com.py.
      - For a site needing a login/JS: use Playwright with the persistent profile at
        `profile_dir` so the user's one-time login persists. See example_playwright.py.
      - Print progress/debug to STDERR (print(..., file=sys.stderr)), never stdout.
    """
    log(f"scraping (project_id={project_id})")

    records: list[dict] = [
        # --- delete this example and build your real records ---
        # {
        #     "key": "UNIQUE-STABLE-ID",          # REQUIRED
        #     "title": "Human readable title",    # REQUIRED
        #     "project_id": project_id,           # or a fixed id, or None for global
        #     "kind": "po",                       # optional subtype
        #     "body": "Longer description text",  # optional
        #     "url": "https://example.com/item",  # optional
        #     "timestamp": "2026-06-18T10:00:00+00:00",  # optional ISO 8601
        #     "data": {"status": "Ordered", "qty": 5},   # optional extra fields
        # },
    ]
    return records


# ----------------------------------------------------------------------------
# Boilerplate below — you normally don't need to change it.
# ----------------------------------------------------------------------------
def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", default=None)
    ap.add_argument("--profile-dir", default=None)
    args = ap.parse_args()

    try:
        records = scrape(args.project_id, args.profile_dir)
    except Exception as exc:  # surface failures as a non-zero exit + stderr log
        log(f"ERROR: {type(exc).__name__}: {exc}")
        return 1

    json.dump(records, sys.stdout)  # the ONLY thing printed to stdout
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
