"""Phase 5 verification: the fetch pipeline end-to-end (offline, deterministic).

Exercises fetch -> parse -> store -> diff -> read directly, then runs the runner CLI as a
real subprocess. Uses a THROWAWAY in-test source defined here — the shipped app contains
no fabricated sources, so the pipeline is proven without baking demo data into the product.

    .venv/Scripts/python.exe scripts/verify_fetch.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fetch_service.models import RawSnapshot, Record  # noqa: E402
from fetch_service.service import refresh_group  # noqa: E402
from fetch_service.source import BaseSource, FetchContext, SourceRegistry  # noqa: E402
from fetch_service.store import Store  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(label: str, ok: bool) -> None:
    checks.append((label, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


class _TestUpdatesSource(BaseSource):
    """A throwaway source for the test only — not registered in the app."""

    id = "test_updates"
    name = "Test Updates"
    group = "updates"
    refresh_after = timedelta(seconds=0)

    def fetch(self, ctx: FetchContext) -> RawSnapshot:
        now = datetime.now(timezone.utc).isoformat()
        items = [
            {"key": "a", "title": "Alpha", "body": "static", "pid": "DEMO-NPDE",
             "ts": "2026-06-16T10:00:00+00:00"},
            {"key": "b", "title": "Beta", "body": "static", "pid": "DEMO-SMALL",
             "ts": "2026-06-15T10:00:00+00:00"},
            {"key": "heartbeat", "title": "Heartbeat", "body": now, "pid": None,
             "ts": now},
        ]
        return RawSnapshot(content=json.dumps(items).encode(), content_type="application/json")

    def parse(self, raw: RawSnapshot) -> list[Record]:
        return [
            Record(source_id=self.id, group=self.group, kind="announcement",
                   key=it["key"], title=it["title"], body=it["body"],
                   project_id=it["pid"], timestamp=datetime.fromisoformat(it["ts"]))
            for it in json.loads(raw.content.decode())
        ]


def main() -> int:
    tmp = Path(tempfile.mkdtemp()) / "store.sqlite3"
    store = Store(tmp)
    registry = SourceRegistry()
    registry.register(_TestUpdatesSource())

    # First refresh -> all new.
    res = refresh_group(store, registry, "updates", force=True)
    added = sum(r.get("added", 0) for r in res)
    check(f"first refresh added records ({added})", added == 3)

    # Second forced refresh -> only the heartbeat body changed -> exactly one change.
    res2 = refresh_group(store, registry, "updates", force=True)
    changed = sum(r.get("changed", 0) for r in res2)
    check(f"diff detected exactly the changed record ({changed})", changed == 1)

    ups = store.get_updates()
    check("update feed has rows", len(ups) > 0)
    npde = store.get_updates(project_id="DEMO-NPDE")
    check("update feed filters by project", bool(npde) and all(u.project_id == "DEMO-NPDE" for u in npde))

    # Self-healing prune: drop data whose source is unknown.
    removed = store.prune_to_sources(set())  # nothing is "known" -> all pruned
    check("prune removes orphaned/unknown-source data", removed > 0 and not store.get_updates())
    store.close()

    # Default app registry ships NO fabricated sources.
    from fetch_service.sources import register_all
    default = register_all(SourceRegistry())
    check("app ships zero fabricated sources by default", len(default.all()) == 0)

    # Runner CLI runs as a separate process (empty group is a clean no-op).
    tmp2 = Path(tempfile.mkdtemp()) / "store2.sqlite3"
    proc = subprocess.run(
        [sys.executable, "-m", "fetch_service.runner", "--group", "updates",
         "--force", "--store", str(tmp2)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=60,
    )
    ok = proc.returncode == 0
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        ran = payload.get("group") == "updates"
    except Exception:
        ran = False
    check("runner CLI ran as subprocess", ok and ran)
    check("runner wrote a store file", tmp2.exists())

    print()
    failed = [l for l, ok in checks if not ok]
    if failed:
        print(f"RESULT: {len(failed)} check(s) failed.")
        return 1
    print(f"RESULT: all {len(checks)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
