"""SQLite connection and DDL bootstrap for :class:`RadarRepository`."""

from __future__ import annotations

import sqlite3

from utils.constants import SQLITE_CONNECTION_TIMEOUT_SECONDS


class SchemaMixin:
    """SQLite connection helper and table bootstrap."""

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS radars (
                    format_name TEXT NOT NULL,
                    archetype_href TEXT NOT NULL,
                    archetype_name TEXT NOT NULL DEFAULT '',
                    generated_at TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    total_decks_analyzed INTEGER NOT NULL DEFAULT 0,
                    decks_failed INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (format_name, archetype_href)
                );

                CREATE TABLE IF NOT EXISTS radar_cards (
                    format_name TEXT NOT NULL,
                    archetype_href TEXT NOT NULL,
                    zone TEXT NOT NULL,
                    card_name TEXT NOT NULL,
                    appearances INTEGER NOT NULL DEFAULT 0,
                    total_copies INTEGER NOT NULL DEFAULT 0,
                    max_copies INTEGER NOT NULL DEFAULT 0,
                    avg_copies REAL NOT NULL DEFAULT 0,
                    inclusion_rate REAL NOT NULL DEFAULT 0,
                    expected_copies REAL NOT NULL DEFAULT 0,
                    copy_distribution_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (format_name, archetype_href, zone, card_name),
                    FOREIGN KEY (format_name, archetype_href)
                        REFERENCES radars (format_name, archetype_href)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_radar_cards_lookup
                    ON radar_cards (
                        format_name,
                        archetype_href,
                        zone,
                        expected_copies DESC,
                        inclusion_rate DESC
                    );
                """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
