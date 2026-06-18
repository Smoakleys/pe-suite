"""The Source contract + registry — the extensibility core of the fetch side.

A source is a self-contained plugin. To add one, write a class with `fetch()` + `parse()`
and register it. Nothing else in the app changes: the service, the store, and both panes
work in terms of `Record`, not in terms of any specific source.

Why fetch/parse are split:
- `fetch()` does I/O and returns a RawSnapshot (stored verbatim).
- `parse()` is pure: RawSnapshot -> list[Record], re-runnable against stored raw bytes.
  When a site's layout changes, you fix `parse()` and replay — no re-scraping, no lost
  history.

`fetch()` is synchronous on purpose: Playwright ships a sync API, so even browser-driven
sources stay simple and need no async plumbing in the service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import RawSnapshot, Record


@dataclass
class FetchContext:
    """Everything a source needs to do its job, handed in by the service."""

    project_id: str | None = None       # refresh scoped to one project, if set
    browser_profile_dir: Path | None = None  # persistent Playwright profile (auth)
    extra: dict = field(default_factory=dict)


@runtime_checkable
class Source(Protocol):
    id: str
    name: str
    group: str                  # sources in a group refresh together (view-driven)
    requires_auth: bool
    refresh_after: timedelta    # staleness window before a re-fetch is worthwhile

    def fetch(self, ctx: FetchContext) -> RawSnapshot: ...
    def parse(self, raw: RawSnapshot) -> list[Record]: ...


class BaseSource:
    """Convenience base with sensible defaults. Subclasses set the class attrs."""

    id: str = ""
    name: str = ""
    group: str = ""
    requires_auth: bool = False
    refresh_after: timedelta = timedelta(minutes=15)

    def fetch(self, ctx: FetchContext) -> RawSnapshot:  # pragma: no cover - abstract
        raise NotImplementedError

    def parse(self, raw: RawSnapshot) -> list[Record]:  # pragma: no cover - abstract
        raise NotImplementedError


class SourceRegistry:
    """Holds the registered sources and answers group queries."""

    def __init__(self) -> None:
        self._sources: dict[str, Source] = {}

    def register(self, source: Source) -> Source:
        if not source.id:
            raise ValueError("source.id is required")
        self._sources[source.id] = source
        return source

    def all(self) -> list[Source]:
        return list(self._sources.values())

    def get(self, source_id: str) -> Source | None:
        return self._sources.get(source_id)

    def in_group(self, group: str) -> list[Source]:
        return [s for s in self._sources.values() if s.group == group]

    def groups(self) -> list[str]:
        return sorted({s.group for s in self._sources.values()})


def build_registry() -> SourceRegistry:
    """Discover and register all sources. Import side-effect free until called."""
    from . import sources  # local import to avoid cycles
    return sources.register_all(SourceRegistry())
