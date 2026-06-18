"""A real HTTP source (stdlib urllib) — proves the framework does genuine network I/O.

Not registered by default (keeps tests/offline runs deterministic). Enable with the
runner's --network flag. It fetches a public page and emits one record from it; the
fetch/parse split means the raw HTML is stored and `parse` can be re-run on it later.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

from ..models import RawSnapshot, Record
from ..source import BaseSource, FetchContext

_URL = "https://example.com/"
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)


class ExampleWebSource(BaseSource):
    id = "web_example"
    name = "Example.com (HTTP demo)"
    group = "updates"
    requires_auth = False
    refresh_after = timedelta(minutes=30)

    def fetch(self, ctx: FetchContext) -> RawSnapshot:
        req = Request(_URL, headers={"User-Agent": "PE-Suite-FetchService/0.1"})
        with urlopen(req, timeout=15) as resp:  # noqa: S310 — fixed trusted URL
            body = resp.read()
            ctype = resp.headers.get("Content-Type", "text/html")
        return RawSnapshot(content=body, content_type=ctype, meta={"url": _URL})

    def parse(self, raw: RawSnapshot) -> list[Record]:
        html = raw.content.decode("utf-8", errors="replace")
        m = _TITLE_RE.search(html)
        title = m.group(1).strip() if m else "(no title)"
        return [Record(
            source_id=self.id, group=self.group, kind="page", key=_URL,
            title=f"{title}", body=f"Fetched {_URL}", url=_URL,
            project_id=None, timestamp=datetime.now(timezone.utc),
            data={"bytes": len(raw.content)},
        )]
