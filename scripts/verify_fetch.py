"""Phase 5 verification: the fetch pipeline end-to-end (offline, deterministic).

Exercises fetch -> parse -> store -> diff -> read directly, then runs the runner CLI as a
real subprocess against a temp store to prove the out-of-process path works.

    .venv/Scripts/python.exe scripts/verify_fetch.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fetch_service.service import refresh_group  # noqa: E402
from fetch_service.source import SourceRegistry  # noqa: E402
from fetch_service.sources import register_all  # noqa: E402
from fetch_service.store import Store  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(label: str, ok: bool) -> None:
    checks.append((label, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


def main() -> int:
    tmp = Path(tempfile.mkdtemp()) / "store.sqlite3"
    store = Store(tmp)
    registry = register_all(SourceRegistry())

    check("two sources registered", len(registry.all()) == 2)

    # First updates refresh -> all new.
    res = refresh_group(store, registry, "updates", force=True)
    added = sum(r.get("added", 0) for r in res)
    check(f"first updates refresh added records ({added})", added >= 4)

    # Second forced refresh -> heartbeat body changed -> a 'changed' update.
    res2 = refresh_group(store, registry, "updates", force=True)
    changed = sum(r.get("changed", 0) for r in res2)
    check(f"re-fetch detected a change via diff ({changed})", changed >= 1)

    # Reads
    ups = store.get_updates()
    check("update feed has rows", len(ups) > 0)
    npde = store.get_updates(project_id="DEMO-NPDE")
    check("update feed filters by project", all(u.project_id == "DEMO-NPDE" for u in npde) and npde)

    # Material group
    refresh_group(store, registry, "material", force=True)
    mats = store.get_records("material", project_id="DEMO-NPDE")
    check("material records stored for project", len(mats) >= 2)
    check("material record carries structured data", bool(mats and mats[0]["data"].get("status")))

    check("source metadata recorded", len(store.list_sources()) == 2)
    store.close()

    # Runner CLI as a separate process against a fresh temp store.
    tmp2 = Path(tempfile.mkdtemp()) / "store2.sqlite3"
    proc = subprocess.run(
        [sys.executable, "-m", "fetch_service.runner", "--group", "updates",
         "--force", "--store", str(tmp2)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=60,
    )
    ok = proc.returncode == 0
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        ran = payload.get("group") == "updates" and len(payload.get("results", [])) == 1
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
