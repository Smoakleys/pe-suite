"""Orchestration: run a source (or a whole group) through fetch -> parse -> store.

This is the per-fetch pipeline. The view-driven refresh model means the UI asks for one
*group* at a time (e.g. "material" when that window opens); the service walks that
group's sources, skips any still-fresh, fetches the rest, diffs into the store, and
records freshness. A failing source is isolated — it records an error status and the
others still run.
"""

from __future__ import annotations

from .paths import browser_profile_dir
from .source import FetchContext, Source, SourceRegistry
from .store import Store


def refresh_source(store: Store, source: Source, project_id: str | None = None,
                   force: bool = False) -> dict:
    store.ensure_source(source.id, source.name, source.group)
    if not force and store.is_fresh(source.id, source.refresh_after.total_seconds()):
        return {"source": source.id, "skipped": True, "reason": "fresh"}

    ctx = FetchContext(project_id=project_id, browser_profile_dir=browser_profile_dir())
    try:
        raw = source.fetch(ctx)
        store.save_raw(source.id, raw.content, raw.content_type, raw.meta)
        records = source.parse(raw)
        diff = store.upsert_records(source.id, records)
        store.mark_fetched(source.id, "ok")
        return {
            "source": source.id, "records": len(records),
            "added": diff.added, "changed": diff.changed, "removed": diff.removed,
        }
    except Exception as exc:  # noqa: BLE001 — isolate per source
        store.mark_fetched(source.id, f"error: {type(exc).__name__}: {exc}")
        return {"source": source.id, "error": f"{type(exc).__name__}: {exc}"}


def refresh_group(store: Store, registry: SourceRegistry, group: str,
                  project_id: str | None = None, force: bool = False) -> list[dict]:
    sources = registry.in_group(group)
    if not sources:
        return [{"group": group, "error": "no sources registered for group"}]
    return [refresh_source(store, s, project_id=project_id, force=force) for s in sources]
