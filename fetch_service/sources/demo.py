"""Deterministic, offline demo sources — prove the pipeline end-to-end without network.

`DemoUpdatesSource` emits a few announcements (some project-tagged) plus a "heartbeat"
record whose body changes every fetch, so a forced re-fetch produces a *changed* update —
exercising the diff/feed path. `DemoMaterialSource` emits fake PO/lot rows per project.

Real sources (HTTP, Playwright) follow the exact same shape; see `web_example.py` and
`playwright_example.py`.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from ..models import RawSnapshot, Record
from ..source import BaseSource, FetchContext


class DemoUpdatesSource(BaseSource):
    id = "demo_updates"
    name = "Demo Updates"
    group = "updates"
    requires_auth = False
    refresh_after = timedelta(minutes=10)

    def fetch(self, ctx: FetchContext) -> RawSnapshot:
        now = datetime.now(timezone.utc)
        # Static records use fixed timestamps so they stay stable across fetches; only
        # the heartbeat changes, which keeps the diff/feed realistic (no false churn).
        items = [
            {"key": "welcome", "kind": "announcement", "project_id": None,
             "title": "Welcome to PE Suite Updates",
             "body": "This feed aggregates updates across sources and projects.",
             "ts": "2026-06-15T09:00:00+00:00"},
            {"key": "npde-fab-note", "kind": "announcement", "project_id": "DEMO-NPDE",
             "title": "Wafer fab schedule confirmed",
             "body": "TAI fab confirmed Lot 1 and Lot 2 start dates.",
             "ts": "2026-06-16T14:00:00+00:00"},
            {"key": "small-parts-note", "kind": "announcement", "project_id": "DEMO-SMALL",
             "title": "Parts order acknowledged",
             "body": "Supplier acknowledged the parts order for the Small Demo Project.",
             "ts": "2026-06-15T18:00:00+00:00"},
            # Changes every fetch -> yields a 'changed' update on a forced refresh.
            {"key": "heartbeat", "kind": "status", "project_id": None,
             "title": "Source heartbeat",
             "body": f"Last successful fetch at {now.isoformat(timespec='seconds')}.",
             "ts": now.isoformat()},
        ]
        return RawSnapshot(content=json.dumps(items).encode("utf-8"),
                           content_type="application/json", meta={"count": len(items)})

    def parse(self, raw: RawSnapshot) -> list[Record]:
        items = json.loads(raw.content.decode("utf-8"))
        out = []
        for it in items:
            out.append(Record(
                source_id=self.id, group=self.group, kind=it["kind"], key=it["key"],
                title=it["title"], body=it["body"], project_id=it["project_id"],
                timestamp=datetime.fromisoformat(it["ts"]),
            ))
        return out


class DemoMaterialSource(BaseSource):
    id = "demo_material"
    name = "Demo Material Tracking"
    group = "material"
    requires_auth = False
    refresh_after = timedelta(minutes=10)

    _ROWS = [
        {"key": "PO-1001", "project_id": "DEMO-NPDE", "title": "Wafer lot WFR-2207",
         "status": "In Transit", "qty": 25, "eta": "2026-07-01", "supplier": "TAI Fab"},
        {"key": "PO-1002", "project_id": "DEMO-NPDE", "title": "Burn-in boards",
         "status": "Ordered", "qty": 12, "eta": "2026-06-26", "supplier": "AIZU"},
        {"key": "PO-2001", "project_id": "DEMO-SMALL", "title": "Prototype parts kit",
         "status": "Delivered", "qty": 1, "eta": "2026-05-21", "supplier": "Acme"},
    ]

    def fetch(self, ctx: FetchContext) -> RawSnapshot:
        return RawSnapshot(content=json.dumps(self._ROWS).encode("utf-8"),
                           content_type="application/json", meta={"count": len(self._ROWS)})

    def parse(self, raw: RawSnapshot) -> list[Record]:
        rows = json.loads(raw.content.decode("utf-8"))
        out = []
        for r in rows:
            out.append(Record(
                source_id=self.id, group=self.group, kind="po", key=r["key"],
                title=r["title"], project_id=r["project_id"],
                body=f"{r['status']} · qty {r['qty']} · ETA {r['eta']}",
                data={"status": r["status"], "qty": r["qty"], "eta": r["eta"],
                      "supplier": r["supplier"], "po": r["key"]},
            ))
        return out
