"""SQLite persistence (architecture §10). One database per world: runs/<world>/store.sqlite.

Every table has explicit key columns plus a `data` JSON column holding the full row, so nothing is lost
and stage code can evolve its payloads without migrations. `upsert` is idempotent.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[tuple[str, str], ...]  # (column, sqlite type) — excludes `data`
    pk: tuple[str, ...]


SCHEMA: dict[str, Table] = {t.name: t for t in [
    Table("messages", (("message_id", "TEXT"), ("thread_id", "TEXT"), ("sent_at", "TEXT"), ("from_addr", "TEXT"),
                       ("subject", "TEXT"), ("is_from_avery", "INTEGER")), ("message_id",)),
    Table("threads", (("thread_id", "TEXT"), ("router_type", "TEXT"), ("latest_at", "TEXT")), ("thread_id",)),
    Table("events", (("event_id", "TEXT"), ("uid", "TEXT"), ("recurrence_id", "TEXT"), ("calendar", "TEXT"),
                     ("start", "TEXT"), ("end", "TEXT"), ("organizer", "TEXT"), ("avery_partstat", "TEXT")), ("event_id",)),
    Table("notes", (("path", "TEXT"), ("mtime", "TEXT"), ("note_date", "TEXT")), ("path",)),
    Table("tasks", (("task_id", "TEXT"), ("title", "TEXT"), ("due", "TEXT"), ("status", "TEXT")), ("task_id",)),
    Table("extractions", (("input_hash", "TEXT"), ("source_id", "TEXT"), ("type", "TEXT"), ("prompt_version", "TEXT"),
                          ("model", "TEXT"), ("created_at", "TEXT")), ("input_hash",)),
    Table("contacts", (("contact_id", "TEXT"), ("category", "TEXT"), ("tier", "TEXT")), ("contact_id",)),
    Table("runs", (("run_id", "TEXT"), ("world", "TEXT"), ("as_of", "TEXT"), ("variant", "TEXT"), ("customize", "TEXT"),
                   ("cost_usd", "REAL"), ("created_at", "TEXT")), ("run_id",)),
    Table("candidates", (("run_id", "TEXT"), ("candidate_id", "TEXT"), ("type", "TEXT"), ("about", "TEXT")), ("run_id", "candidate_id")),
    Table("triage_results", (("run_id", "TEXT"), ("candidate_id", "TEXT"), ("include", "INTEGER"), ("priority", "TEXT"),
                             ("section", "TEXT")), ("run_id", "candidate_id")),
    Table("digest_items", (("run_id", "TEXT"), ("item_id", "TEXT"), ("about", "TEXT"), ("surfaced", "INTEGER"),
                           ("section", "TEXT"), ("priority", "TEXT"), ("resolved_later", "INTEGER"),
                           ("times_surfaced", "INTEGER")), ("run_id", "item_id")),
    Table("rulings", (("id", "TEXT"), ("ruling", "TEXT"), ("option_chosen", "INTEGER"), ("from_question", "TEXT"),
                      ("created", "TEXT"), ("expires", "TEXT")), ("id",)),
]}


def _cell(v: Any) -> Any:
    if isinstance(v, bool):
        return int(v)
    if v is None or isinstance(v, (int, float, str)):
        return v
    return json.dumps(v, default=str)


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------ lifecycle
    def connect(self) -> Store:
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self.init_schema()
        return self

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Store:
        return self.connect()

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        return self._conn

    def init_schema(self) -> None:
        for t in SCHEMA.values():
            cols = ", ".join(f"{c} {typ}" for c, typ in t.columns) + ", data TEXT NOT NULL"
            self.conn.execute(f"CREATE TABLE IF NOT EXISTS {t.name} ({cols}, PRIMARY KEY ({', '.join(t.pk)}))")
        self.conn.commit()

    # ------------------------------------------------------------------ rows
    def upsert(self, table: str, row: dict) -> None:
        t = SCHEMA[table]
        cols = [c for c, _ in t.columns]
        values = [_cell(row.get(c)) for c in cols] + [json.dumps(row, default=str, ensure_ascii=False)]
        names = cols + ["data"]
        updates = ", ".join(f"{c}=excluded.{c}" for c in names if c not in t.pk)
        sql = (f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)}) "
               f"ON CONFLICT({', '.join(t.pk)}) DO UPDATE SET {updates}")
        self.conn.execute(sql, values)

    def upsert_many(self, table: str, rows: Iterable[dict]) -> int:
        n = 0
        for r in rows:
            self.upsert(table, r)
            n += 1
        self.conn.commit()
        return n

    def commit(self) -> None:
        self.conn.commit()

    @staticmethod
    def _row(r: sqlite3.Row) -> dict:
        d = dict(r)
        data = json.loads(d.pop("data") or "{}")
        data.update({k: v for k, v in d.items() if k not in data})
        return data

    def get(self, table: str, **key: Any) -> dict | None:
        where = " AND ".join(f"{k}=?" for k in key)
        cur = self.conn.execute(f"SELECT * FROM {table} WHERE {where}", tuple(key.values()))
        r = cur.fetchone()
        return self._row(r) if r else None

    def query(self, table: str, where: str = "", params: tuple = (), order: str = "") -> list[dict]:
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        if order:
            sql += f" ORDER BY {order}"
        return [self._row(r) for r in self.conn.execute(sql, params)]

    def count(self, table: str) -> int:
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def tables(self) -> list[str]:
        return sorted(SCHEMA)
