"""SQLite connection and DDL bootstrap for :class:`FormatCardPoolRepository`."""

from __future__ import annotations

import sqlite3
import threading
from typing import TYPE_CHECKING

from utils.constants import SQLITE_CONNECTION_TIMEOUT_SECONDS

if TYPE_CHECKING:
    from repositories.format_card_pool_repository.protocol import (
        FormatCardPoolRepositoryProto,
    )

    _Base = FormatCardPoolRepositoryProto
else:
    _Base = object


class SchemaMixin(_Base):
    """SQLite connection helper and table bootstrap."""

    def _initialize(self) -> None:
        # Lock guards the shared read connection and the read-side memo caches.
        self._read_lock = threading.RLock()
        self._read_conn_obj: sqlite3.Connection | None = None
        self._summary_cache = {}
        self._card_total_cache = {}
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS format_card_pools (
                    format_name TEXT PRIMARY KEY,
                    generated_at TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    total_decks_analyzed INTEGER NOT NULL DEFAULT 0,
                    decks_failed INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS format_card_pool_cards (
                    format_name TEXT NOT NULL,
                    card_name TEXT NOT NULL,
                    copies_played INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (format_name, card_name),
                    FOREIGN KEY (format_name)
                        REFERENCES format_card_pools (format_name)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_format_card_pool_cards_top
                    ON format_card_pool_cards (format_name, copies_played DESC, card_name ASC);
                """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _read_connection(self) -> sqlite3.Connection:
        """Return a persistent connection reused across read queries.

        Reopening a fresh ``sqlite3.connect`` per query dominates the cost of
        the small lookups issued on every card hover/selection, so reads share
        a single long-lived connection. ``check_same_thread=False`` lets the
        background worker reuse it too; all access is serialized via
        ``self._read_lock``.
        """
        conn = self._read_conn_obj
        if conn is None:
            conn = sqlite3.connect(
                self.db_path,
                timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS,
                check_same_thread=False,
            )
            conn.execute("PRAGMA foreign_keys = ON")
            self._read_conn_obj = conn
        return conn

    def _invalidate_read_state(self) -> None:
        """Drop memoized reads and recycle the shared read connection.

        Called after writes so the next read observes the new snapshot rather
        than a stale cached value or a connection holding an old read view.
        """
        with self._read_lock:
            self._summary_cache.clear()
            self._card_total_cache.clear()
            conn = self._read_conn_obj
            self._read_conn_obj = None
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
