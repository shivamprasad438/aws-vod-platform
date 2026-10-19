"""Tiny SQLite metadata store.

SQLite keeps the project easy to run. For more than one replica, swap this module
for Amazon RDS/DynamoDB (see README, "Production notes").
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    original_filename TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata TEXT,
    renditions TEXT,
    playback_url TEXT,
    error TEXT
)
"""


class VideoDB:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._conn() as conn:
            conn.execute(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def insert(self, video_id: str, title: str, filename: str, created_at: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO videos (id, title, original_filename, status, created_at) "
                "VALUES (?, ?, ?, 'processing', ?)",
                (video_id, title, filename, created_at),
            )

    def mark_ready(self, video_id: str, metadata: dict, renditions: list, url: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE videos SET status='ready', metadata=?, renditions=?, playback_url=? "
                "WHERE id=?",
                (json.dumps(metadata), json.dumps(renditions), url, video_id),
            )

    def mark_failed(self, video_id: str, error: str) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE videos SET status='failed', error=? WHERE id=?", (error, video_id))

    def get(self, video_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        return self._to_dict(row) if row else None

    def list(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM videos ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._to_dict(r) for r in rows]

    def ping(self) -> bool:
        with self._conn() as conn:
            conn.execute("SELECT 1")
        return True

    @staticmethod
    def _to_dict(row: sqlite3.Row) -> dict:
        data = dict(row)
        data["metadata"] = json.loads(data["metadata"]) if data["metadata"] else None
        data["renditions"] = json.loads(data["renditions"]) if data["renditions"] else None
        return data
