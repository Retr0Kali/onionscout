"""A tiny SQLite page cache so repeated fetches don't re-hit Tor."""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing

from .config import Config, get_config
from .utils import normalize_url


class PageCache:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or get_config()
        self.enabled = self.cfg.cache_enabled
        self.path = self.cfg.cache_path
        self.ttl = self.cfg.cache_ttl
        if self.enabled:
            self._init_db()

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pages (
                    url        TEXT PRIMARY KEY,
                    status     INTEGER,
                    content    TEXT,
                    fetched_at REAL
                )
                """
            )
            conn.commit()

    def get(self, url: str) -> tuple[int, str] | None:
        """Return (status, content) if a fresh entry exists, else None."""
        if not self.enabled:
            return None
        key = normalize_url(url)
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute(
                "SELECT status, content, fetched_at FROM pages WHERE url = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        status, content, fetched_at = row
        if self.ttl and (time.time() - fetched_at) > self.ttl:
            return None
        return status, content

    def put(self, url: str, status: int, content: str) -> None:
        if not self.enabled:
            return
        key = normalize_url(url)
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pages (url, status, content, fetched_at) "
                "VALUES (?, ?, ?, ?)",
                (key, status, content, time.time()),
            )
            conn.commit()

    def clear(self) -> int:
        if not self.enabled:
            return 0
        with closing(sqlite3.connect(self.path)) as conn:
            cur = conn.execute("DELETE FROM pages")
            conn.commit()
            return cur.rowcount
