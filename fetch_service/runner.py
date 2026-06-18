"""Runner: the fetch service's process entry point.

The UI never fetches in-process. Instead it spawns this as a separate process for one
group at a time (view-driven), e.g.:

    python -m fetch_service.runner --group updates --force
    python -m fetch_service.runner --group material --project DEMO-NPDE

It prints a JSON summary to stdout and exits. Network/Playwright sources are opt-in.
"""

from __future__ import annotations

import argparse
import json
import sys

from .paths import fetch_store_path
from .service import refresh_group
from .source import SourceRegistry
from .sources import register_all
from .store import Store


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fetch_service.runner")
    ap.add_argument("--group", required=True, help="source group to refresh")
    ap.add_argument("--project", default=None, help="scope refresh to a project id")
    ap.add_argument("--force", action="store_true", help="ignore freshness window")
    ap.add_argument("--network", action="store_true", help="include HTTP sources")
    ap.add_argument("--playwright", action="store_true", help="include Playwright sources")
    ap.add_argument("--store", default=None, help="override store path (testing)")
    args = ap.parse_args(argv)

    store = Store(args.store or fetch_store_path())
    registry = register_all(SourceRegistry(),
                            include_network=args.network,
                            include_playwright=args.playwright)
    results = refresh_group(store, registry, args.group,
                            project_id=args.project, force=args.force)
    store.close()

    print(json.dumps({"group": args.group, "results": results}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
