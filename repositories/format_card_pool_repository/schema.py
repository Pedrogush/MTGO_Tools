"""SQLite connection and DDL bootstrap for :class:`FormatCardPoolRepository`."""

from __future__ import annotations

import sqlite3
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
