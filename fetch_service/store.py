"""The hidden SQLite store: normalized records, raw snapshots, and the update feed.

One opaque file under %LOCALAPPDATA%\\PESuite — never shown to users, never in the
projects folder. WAL mode lets the UI read while the runner process writes.

`upsert_records` is where diffing happens: comparing each source's new records (by
`key` + content hash) against what's stored yields new / changed / removed events, which
are appended to the `updates` feed the Updates pane reads.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import Record, SourceInfo, UpdateRow

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id              TEXT PRIMARY KEY,
    name            TEXT,
    "group"         TEXT,
    last_fetched_at TEXT,
    last_status     TEXT
);

CREATE TABLE IF NOT EXISTS raw_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id    TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,
    content      BLOB,
    content_type TEXT,
    meta         TEXT
);
CREATE INDEX IF NOT EXISTS idx_raw_source ON raw_snapshots(source_id, fetched_at);

CREATE TABLE IF NOT EXISTS records (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id    TEXT NOT NULL,
    "group"      TEXT,
    kind         TEXT,
    rec_key      TEXT NOT NULL,
    project_id   TEXT,
    title        TEXT,
    body         TEXT,
    url          TEXT,
    ts           TEXT,
    data         TEXT,
    content_hash TEXT,
    first_seen   TEXT,
    last_seen    TEXT,
    UNIQUE(source_id, rec_key)
);
CREATE INDEX IF NOT EXISTS idx_rec_group ON records("group", project_id);

CREATE TABLE IF NOT EXISTS updates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   TEXT NOT NULL,
    project_id  TEXT,
    change_type TEXT,
    title       TEXT,
    summary     TEXT,
    url         TEXT,
    at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_upd_at ON updates(at);
"""

_RAW_KEEP = 5  # raw snapshots retained per source


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


@dataclass
class Diff:
    added: int = 0
    changed: int = 0
    removed: int = 0

    @property
    def total(self) -> int:
        return self.added + self.changed + self.removed


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(self.path))
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA foreign_keys=ON")
        self._con.executescript(_SCHEMA)
        self._con.commit()

    def close(self) -> None:
        self._con.close()

    def prune_to_sources(self, known_ids) -> int:
        """Delete all data whose source is not in `known_ids`.

        Makes the store self-healing: when a source is removed from the codebase, its
        stale records / raw snapshots / update-feed rows disappear on the next startup,
        so no fabricated or orphaned data ever lingers. Returns rows removed.
        """
        known = set(known_ids)
        removed = 0
        for table in ("records", "raw_snapshots", "updates", "sources"):
            id_col = "id" if table == "sources" else "source_id"
            existing = {r[0] for r in self._con.execute(f"SELECT {id_col} FROM {table}")}
            stale = existing - known
            for sid in stale:
                cur = self._con.execute(f"DELETE FROM {table} WHERE {id_col}=?", (sid,))
                removed += cur.rowcount
        self._con.commit()
        return removed

    # -- writes (runner side) -------------------------------------------
    def ensure_source(self, source_id: str, name: str, group: str) -> None:
        self._con.execute(
            'INSERT INTO sources(id, name, "group") VALUES(?,?,?) '
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, \"group\"=excluded.\"group\"",
            (source_id, name, group),
        )
        self._con.commit()

    def save_raw(self, source_id: str, content: bytes, content_type: str, meta: dict) -> None:
        self._con.execute(
            "INSERT INTO raw_snapshots(source_id, fetched_at, content, content_type, meta) "
            "VALUES(?,?,?,?,?)",
            (source_id, _now(), content, content_type, json.dumps(meta)),
        )
        # keep only the most recent N per source
        self._con.execute(
            "DELETE FROM raw_snapshots WHERE source_id=? AND id NOT IN "
            "(SELECT id FROM raw_snapshots WHERE source_id=? ORDER BY id DESC LIMIT ?)",
            (source_id, source_id, _RAW_KEEP),
        )
        self._con.commit()

    def upsert_records(self, source_id: str, records: list[Record]) -> Diff:
        """Insert/update records for a source and append diff events to the feed."""
        now = _now()
        diff = Diff()
        seen_keys: set[str] = set()

        existing = {
            r["rec_key"]: r
            for r in self._con.execute(
                "SELECT rec_key, content_hash FROM records WHERE source_id=?", (source_id,)
            )
        }

        for rec in records:
            seen_keys.add(rec.key)
            chash = rec.content_hash()
            ts = rec.timestamp.isoformat() if rec.timestamp else None
            prior = existing.get(rec.key)
            if prior is None:
                self._con.execute(
                    'INSERT INTO records(source_id,"group",kind,rec_key,project_id,title,'
                    "body,url,ts,data,content_hash,first_seen,last_seen) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (source_id, rec.group, rec.kind, rec.key, rec.project_id, rec.title,
                     rec.body, rec.url, ts, json.dumps(rec.data), chash, now, now),
                )
                self._add_update(source_id, rec.project_id, "new",
                                 rec.title, rec.body[:200], rec.url, ts or now)
                diff.added += 1
            elif prior["content_hash"] != chash:
                self._con.execute(
                    'UPDATE records SET "group"=?,kind=?,project_id=?,title=?,body=?,url=?,'
                    "ts=?,data=?,content_hash=?,last_seen=? WHERE source_id=? AND rec_key=?",
                    (rec.group, rec.kind, rec.project_id, rec.title, rec.body, rec.url, ts,
                     json.dumps(rec.data), chash, now, source_id, rec.key),
                )
                self._add_update(source_id, rec.project_id, "changed",
                                 rec.title, rec.body[:200], rec.url, ts or now)
                diff.changed += 1
            else:
                self._con.execute(
                    "UPDATE records SET last_seen=? WHERE source_id=? AND rec_key=?",
                    (now, source_id, rec.key),
                )

        # removed = keys we had before but didn't see this fetch
        for key in set(existing) - seen_keys:
            row = self._con.execute(
                "SELECT title, project_id, url FROM records WHERE source_id=? AND rec_key=?",
                (source_id, key),
            ).fetchone()
            if row:
                self._add_update(source_id, row["project_id"], "removed",
                                 row["title"], "No longer reported by the source.",
                                 row["url"], now)
            self._con.execute(
                "DELETE FROM records WHERE source_id=? AND rec_key=?", (source_id, key)
            )
            diff.removed += 1

        self._con.commit()
        return diff

    def _add_update(self, source_id, project_id, change_type, title, summary, url, at) -> None:
        self._con.execute(
            "INSERT INTO updates(source_id,project_id,change_type,title,summary,url,at) "
            "VALUES(?,?,?,?,?,?,?)",
            (source_id, project_id, change_type, title, summary, url, at),
        )

    def mark_fetched(self, source_id: str, status: str = "ok") -> None:
        self._con.execute(
            "UPDATE sources SET last_fetched_at=?, last_status=? WHERE id=?",
            (_now(), status, source_id),
        )
        self._con.commit()

    def is_fresh(self, source_id: str, within_seconds: float) -> bool:
        row = self._con.execute(
            "SELECT last_fetched_at FROM sources WHERE id=?", (source_id,)
        ).fetchone()
        last = _parse_dt(row["last_fetched_at"]) if row else None
        if last is None:
            return False
        age = (datetime.now(timezone.utc) - last).total_seconds()
        return age < within_seconds

    # -- reads (UI side) ------------------------------------------------
    def list_sources(self) -> list[SourceInfo]:
        rows = self._con.execute(
            'SELECT id, name, "group", last_fetched_at, last_status FROM sources ORDER BY name'
        )
        return [
            SourceInfo(r["id"], r["name"], r["group"],
                       _parse_dt(r["last_fetched_at"]), r["last_status"])
            for r in rows
        ]

    def get_updates(self, project_id: str | None = None, source_id: str | None = None,
                    limit: int = 200) -> list[UpdateRow]:
        sql = "SELECT * FROM updates"
        clauses, args = [], []
        if project_id is not None:
            clauses.append("project_id=?")
            args.append(project_id)
        if source_id is not None:
            clauses.append("source_id=?")
            args.append(source_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY at DESC, id DESC LIMIT ?"
        args.append(limit)
        return [
            UpdateRow(r["id"], r["source_id"], r["project_id"], r["change_type"],
                      r["title"], r["summary"], _parse_dt(r["at"]), r["url"])
            for r in self._con.execute(sql, args)
        ]

    def get_records(self, group: str, project_id: str | None = None) -> list[dict]:
        sql = 'SELECT * FROM records WHERE "group"=?'
        args: list = [group]
        if project_id is not None:
            sql += " AND project_id=?"
            args.append(project_id)
        sql += " ORDER BY ts DESC, id DESC"
        out = []
        for r in self._con.execute(sql, args):
            d = dict(r)
            d["data"] = json.loads(d["data"]) if d["data"] else {}
            out.append(d)
        return out
