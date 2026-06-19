"""WORKED EXAMPLE scraper — real HTTP, no fabricated data.

Fetches https://example.com and emits ONE record carrying its <title>. This is a
complete, runnable reference for the template. Test it standalone:

    python fetch_service/sources/scripts/example_com.py

It should print a one-element JSON array. Copy its shape for real sources.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen

URL = "https://example.com/"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def scrape(project_id: str | None, profile_dir: str | None) -> list[dict]:
    log(f"GET {URL}")
    req = Request(URL, headers={"User-Agent": "PE-Suite-Scraper/1.0"})
    with urlopen(req, timeout=15) as resp:          # noqa: S310 — fixed trusted URL
        html = resp.read().decode("utf-8", errors="replace")

    m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = (m.group(1).strip() if m else "(no title)")
    log(f"parsed title: {title!r}")

    return [{
        "key": URL,                                  # stable id for this item
        "title": title,
        "project_id": project_id,                    # global if None
        "kind": "page",
        "body": f"Fetched {URL} ({len(html)} bytes).",
        "url": URL,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"bytes": len(html)},
    }]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", default=None)
    ap.add_argument("--profile-dir", default=None)
    args = ap.parse_args()
    try:
        records = scrape(args.project_id, args.profile_dir)
    except Exception as exc:
        log(f"ERROR: {type(exc).__name__}: {exc}")
        return 1
    json.dump(records, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
