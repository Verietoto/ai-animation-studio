import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    parent_image_id TEXT,
    kind TEXT NOT NULL,            -- upload | edit | frame
    prompt TEXT,
    model TEXT,
    path TEXT NOT NULL,
    width INTEGER, height INTEGER,
    cost REAL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY,
    parent_clip_id TEXT,
    source_image_id TEXT,
    prompt TEXT NOT NULL,
    model TEXT NOT NULL,
    params TEXT NOT NULL,          -- JSON
    status TEXT NOT NULL,          -- submitted | in_progress | completed | failed | failed_download
    remote_job_id TEXT,
    path TEXT,
    merged_path TEXT,
    cost REAL,
    error TEXT,
    chain_depth INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)

    def execute(self, sql: str, args: tuple = ()) -> None:
        with self._lock:
            self._conn.execute(sql, args)
            self._conn.commit()

    def one(self, sql: str, args: tuple = ()) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(sql, args).fetchone()
        return dict(row) if row else None

    def all(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    def insert(self, table: str, values: dict[str, Any]) -> None:
        cols = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        self.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(values.values()))

    def update(self, table: str, id_: str, values: dict[str, Any]) -> None:
        sets = ", ".join(f"{k} = ?" for k in values)
        self.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*values.values(), id_))

    def spent_today(self) -> float:
        day = datetime.now(timezone.utc).date().isoformat()
        total = 0.0
        for table in ("clips", "images"):
            row = self.one(
                f"SELECT COALESCE(SUM(cost), 0) AS s FROM {table} WHERE created_at >= ?", (day,)
            )
            total += row["s"] if row else 0.0
        return total
