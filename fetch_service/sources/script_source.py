"""ScriptSource — run an external scraper script and ingest its JSON output.

This is the low-cognitive-load path for adding a web-scraping source. Instead of writing
a class that understands the store, diffing, Playwright, and Qt, a contributor writes ONE
standalone Python script that scrapes a site and prints a JSON array of records to stdout.
A `ScriptSource` wraps that script: it runs it as a subprocess, captures stdout (the data)
and stderr (logs), and converts the JSON into normalized `Record`s.

See docs/SCRAPER_PLAYBOOK.md for the step-by-step contributor guide.

Output contract the script MUST follow — print to stdout a JSON array of objects:

    [
      {
        "key":        "PO-1001",            # REQUIRED: stable unique id (drives diffing)
        "title":      "Wafer lot WFR-2207", # REQUIRED: short human label
        "project_id": "DEMO-NPDE",          # optional: which project (null = global)
        "kind":       "po",                 # optional: subtype within the group
        "body":       "In transit, ETA …",  # optional: longer text
        "url":        "https://…",          # optional: link
        "timestamp":  "2026-06-18T10:00:00+00:00",  # optional: ISO 8601 event time
        "data":       {"status": "In Transit", "qty": 25, "eta": "2026-07-01",
                       "supplier": "TAI Fab", "po": "PO-1001"}   # optional extras
      }
    ]

The script receives optional CLI args it MAY use or ignore:
    --project-id <id>     the project the refresh is scoped to (if any)
    --profile-dir <path>  a persistent browser-profile dir (for Playwright logins)

stdout = data (the JSON array). stderr = human logs (captured for debugging).
A non-zero exit code (or non-JSON stdout) is treated as a failed fetch.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from ..models import RawSnapshot, Record
from ..source import BaseSource, FetchContext

SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"


class ScriptSource(BaseSource):
    """Adapts a standalone scraper script to the Source contract."""

    def __init__(self, id: str, name: str, group: str, script: str,
                 requires_auth: bool = False,
                 refresh_after: timedelta = timedelta(minutes=30),
                 timeout: int = 180) -> None:
        self.id = id
        self.name = name
        self.group = group
        self.script = script              # filename inside SCRIPTS_DIR, or an abs path
        self.requires_auth = requires_auth
        self.refresh_after = refresh_after
        self.timeout = timeout

    def _script_path(self) -> Path:
        p = Path(self.script)
        return p if p.is_absolute() else SCRIPTS_DIR / self.script

    def fetch(self, ctx: FetchContext) -> RawSnapshot:
        script = self._script_path()
        if not script.exists():
            raise FileNotFoundError(f"scraper script not found: {script}")

        cmd = [sys.executable, str(script)]
        if ctx.project_id:
            cmd += ["--project-id", ctx.project_id]
        if ctx.browser_profile_dir:
            cmd += ["--profile-dir", str(ctx.browser_profile_dir)]

        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=self.timeout,
            cwd=str(script.parent),
        )
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip()[-600:]
            raise RuntimeError(f"scraper '{self.script}' exited {proc.returncode}: {tail}")

        return RawSnapshot(
            content=(proc.stdout or "").encode("utf-8"),
            content_type="application/json",
            meta={"script": self.script, "log": (proc.stderr or "")[-4000:]},
        )

    def parse(self, raw: RawSnapshot) -> list[Record]:
        text = raw.content.decode("utf-8").strip() or "[]"
        try:
            items = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"scraper '{self.script}' did not print valid JSON to stdout: {exc}"
            ) from None
        if not isinstance(items, list):
            raise ValueError(f"scraper '{self.script}' must print a JSON ARRAY of records")

        records: list[Record] = []
        for i, it in enumerate(items):
            if "key" not in it or "title" not in it:
                raise ValueError(
                    f"scraper '{self.script}' record #{i} missing required 'key'/'title'"
                )
            ts = it.get("timestamp")
            records.append(Record(
                source_id=self.id,
                group=self.group,
                kind=it.get("kind", "item"),
                key=str(it["key"]),
                title=str(it["title"]),
                body=str(it.get("body", "")),
                url=it.get("url"),
                project_id=it.get("project_id"),
                timestamp=datetime.fromisoformat(ts) if ts else None,
                data=it.get("data", {}) or {},
            ))
        return records
