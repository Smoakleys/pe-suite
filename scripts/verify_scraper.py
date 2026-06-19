"""Verify the ScriptSource path: external scraper script -> Record pipeline.

Offline and deterministic. Writes throwaway scraper scripts to a temp dir, points a
ScriptSource at them, and runs them through fetch -> parse -> store -> diff. Also checks
the template runs and the output-contract errors are reported clearly.

    .venv/Scripts/python.exe scripts/verify_scraper.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fetch_service.service import refresh_source  # noqa: E402
from fetch_service.source import FetchContext, SourceRegistry  # noqa: E402
from fetch_service.sources import all_known_source_ids, register_all  # noqa: E402
from fetch_service.sources.script_source import SCRIPTS_DIR, ScriptSource  # noqa: E402
from fetch_service.store import Store  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(label: str, ok: bool) -> None:
    checks.append((label, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


def write_script(tmp: Path, name: str, body: str) -> Path:
    p = tmp / name
    p.write_text(body, encoding="utf-8")
    return p


def main() -> int:
    tmp = Path(tempfile.mkdtemp())

    # 1) The shipped template runs and prints a valid JSON array.
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "_template_scraper.py")],
        capture_output=True, text=True, timeout=30,
    )
    try:
        out = json.loads(proc.stdout)
        ok_template = proc.returncode == 0 and isinstance(out, list)
    except Exception:
        ok_template = False
    check("template scraper runs and prints a JSON array", ok_template)

    # 2) A ScriptSource over a 2-record script: fetch -> parse -> store.
    two = write_script(tmp, "two.py", (
        "import json,sys\n"
        "print(json.dumps(["
        "{'key':'A','title':'Alpha','project_id':'DEMO-NPDE','data':{'status':'Ordered'}},"
        "{'key':'B','title':'Beta'}"
        "]).replace(\"'\",'\"'))\n"
    ))
    store = Store(tmp / "store.sqlite3")
    src = ScriptSource(id="t_two", name="Two", group="material", script=str(two))
    res = refresh_source(store, src, force=True)
    check(f"ScriptSource ingested script records ({res.get('added')})", res.get("added") == 2)
    mats = store.get_records("material")
    check("structured 'data' carried through", any(m["data"].get("status") == "Ordered" for m in mats))

    # 3) Change one record's content -> diff reports exactly one change.
    two.write_text(
        "import json,sys\n"
        "print(json.dumps(["
        "{'key':'A','title':'Alpha CHANGED','project_id':'DEMO-NPDE'},"
        "{'key':'B','title':'Beta'}"
        "]).replace(\"'\",'\"'))\n", encoding="utf-8")
    res2 = refresh_source(store, src, force=True)
    check(f"re-run diffed exactly one change ({res2.get('changed')})", res2.get("changed") == 1)
    store.close()

    # 4) Contract violations are reported as failed fetches (not crashes).
    badjson = write_script(tmp, "bad.py", "print('not json at all')\n")
    store2 = Store(tmp / "s2.sqlite3")
    r = refresh_source(store2, ScriptSource("t_bad", "Bad", "updates", str(badjson)), force=True)
    check("non-JSON stdout reported as error", "error" in r)

    nokey = write_script(tmp, "nokey.py",
                         "import json;print(json.dumps([{'title':'no key here'}]).replace(chr(39),chr(34)))\n")
    r2 = refresh_source(store2, ScriptSource("t_nokey", "NoKey", "updates", str(nokey)), force=True)
    check("missing required field reported as error", "error" in r2)
    store2.close()

    # 5) The worked example is registered (opt-in) and known to the prune.
    reg = register_all(SourceRegistry(), include_network=True)
    check("example_com registered under --network", reg.get("example_com") is not None)
    check("example_com is a known source id", "example_com" in all_known_source_ids())

    print()
    failed = [l for l, ok in checks if not ok]
    if failed:
        print(f"RESULT: {len(failed)} check(s) failed.")
        return 1
    print(f"RESULT: all {len(checks)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
