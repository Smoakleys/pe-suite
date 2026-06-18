"""Data model for the fetch side — the normalized currency every source produces.

`RawSnapshot` is exactly what a source pulled (stored verbatim so parsing can be
replayed later). `Record` is the normalized, source-agnostic unit that Updates and
Material Tracking both consume — tagged with `source`, `group`, `project`, and a stable
`key` used for diffing. Read DTOs (`UpdateRow`, `SourceInfo`) are what the UI reads back.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawSnapshot:
    """The raw bytes a source fetched, stored verbatim for replay/debugging."""

    content: bytes
    content_type: str = "text/plain"
    meta: dict = field(default_factory=dict)
    fetched_at: datetime | None = None


@dataclass
class Record:
    """A normalized item. One shape for all sources, all panes.

    `key` is the source-stable identity used for diffing across fetches (e.g. a PO
    number, a ticket id, a URL). Two fetches with the same key but different content
    produce a "changed" update; a new key produces a "new" update.
    """

    source_id: str
    group: str                 # "updates" | "material" | ...
    kind: str                  # finer type within a group ("po", "lot", "announcement")
    key: str                   # stable identity within the source
    title: str
    body: str = ""
    url: str | None = None
    project_id: str | None = None   # which project this pertains to (None = global)
    timestamp: datetime | None = None  # source event time
    data: dict = field(default_factory=dict)  # arbitrary extra fields

    def content_hash(self) -> str:
        """Hash of the user-visible content — drives change detection."""
        payload = json.dumps(
            {
                "title": self.title,
                "body": self.body,
                "url": self.url,
                "project_id": self.project_id,
                "timestamp": self.timestamp.isoformat() if self.timestamp else None,
                "data": self.data,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class UpdateRow:
    """A change event for the Updates pane (read DTO)."""

    id: int
    source_id: str
    project_id: str | None
    change_type: str           # "new" | "changed" | "removed"
    title: str
    summary: str
    at: datetime | None
    url: str | None


@dataclass(frozen=True)
class SourceInfo:
    """Registered-source metadata for filters/status (read DTO)."""

    id: str
    name: str
    group: str
    last_fetched_at: datetime | None
    last_status: str | None
