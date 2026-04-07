"""Repository for locally cached format card-pool snapshots."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from utils.constants import FORMAT_CARD_POOL_DB_FILE, SQLITE_CONNECTION_TIMEOUT_SECONDS


@dataclass(frozen=True)
class FormatCardPoolSummary:
    """Metadata for one locally cached format card pool."""

    format_name: str
    generated_at: str
    source: str
    total_decks_analyzed: int
    decks_failed: int
    unique_cards: int


@dataclass(frozen=True)
class FormatCardPoolCardTotal:
    """Aggregated copy-total entry for a card in one format."""

    card_name: str
    copies_played: int


class FormatCardPoolRepository:
    """Read and write locally cached format card-pool snapshots."""

    def __init__(self, db_path: Path = FORMAT_CARD_POOL_DB_FILE) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def replace_format_pool(self, entry: dict[str, Any]) -> bool:
        format_name = str(entry.get("format", "")).strip().lower()
        cards = entry.get("cards")
        if not format_name or not isinstance(cards, list):
            return False

        rows: dict[str, int] = {}
        for card_name in cards:
            normalized = str(card_name).strip()
            if normalized:
                rows.setdefault(normalized, 0)

        for item in entry.get("copy_totals", []) or []:
            if not isinstance(item, dict):
                continue
            card_name = str(item.get("card_name", "")).strip()
            if not card_name:
                continue
            try:
                copies_played = int(item.get("copies_played", 0) or 0)
            except (TypeError, ValueError):
                copies_played = 0
            rows[card_name] = copies_played

        with self._connect() as conn:
            conn.execute("BEGIN")
            conn.execute("DELETE FROM format_card_pool_cards WHERE format_name = ?", (format_name,))
            conn.execute("DELETE FROM format_card_pools WHERE format_name = ?", (format_name,))
            conn.execute(
                """
                INSERT INTO format_card_pools (
                    format_name,
                    generated_at,
                    source,
                    total_decks_analyzed,
                    decks_failed
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    format_name,
                    str(entry.get("generated_at", "")).strip(),
                    str(entry.get("source", "")).strip(),
                    int(entry.get("total_decks_analyzed", 0) or 0),
                    int(entry.get("decks_failed", 0) or 0),
                ),
            )
            conn.executemany(
                """
                INSERT INTO format_card_pool_cards (format_name, card_name, copies_played)
                VALUES (?, ?, ?)
                """,
                [
                    (format_name, card_name, copies_played)
                    for card_name, copies_played in rows.items()
                ],
            )
            conn.commit()
        return True

    def bulk_replace(self, entries: list[dict[str, Any]]) -> int:
        replaced = 0
        for entry in entries:
            try:
                replaced += int(self.replace_format_pool(entry))
            except Exception as exc:
                logger.warning(f"Failed to replace format card pool: {exc}")
        return replaced

    def has_format_pool(self, format_name: str) -> bool:
        fmt = format_name.strip().lower()
        if not fmt:
            return False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM format_card_pools WHERE format_name = ? LIMIT 1",
                (fmt,),
            ).fetchone()
        return row is not None

    def get_card_names(self, format_name: str) -> set[str]:
        fmt = format_name.strip().lower()
        if not fmt:
            return set()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT card_name
                FROM format_card_pool_cards
                WHERE format_name = ?
                """,
                (fmt,),
            ).fetchall()
        return {str(row[0]) for row in rows}

    def get_top_cards(self, format_name: str, limit: int = 100) -> list[FormatCardPoolCardTotal]:
        fmt = format_name.strip().lower()
        if not fmt:
            return []
        limit = max(1, int(limit))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT card_name, copies_played
                FROM format_card_pool_cards
                WHERE format_name = ? AND copies_played > 0
                ORDER BY copies_played DESC, card_name ASC
                LIMIT ?
                """,
                (fmt, limit),
            ).fetchall()
        return [
            FormatCardPoolCardTotal(card_name=row[0], copies_played=int(row[1])) for row in rows
        ]

    def get_summary(self, format_name: str) -> FormatCardPoolSummary | None:
        fmt = format_name.strip().lower()
        if not fmt:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    p.format_name,
                    p.generated_at,
                    p.source,
                    p.total_decks_analyzed,
                    p.decks_failed,
                    COUNT(c.card_name) AS unique_cards
                FROM format_card_pools AS p
                LEFT JOIN format_card_pool_cards AS c
                    ON c.format_name = p.format_name
                WHERE p.format_name = ?
                GROUP BY
                    p.format_name,
                    p.generated_at,
                    p.source,
                    p.total_decks_analyzed,
                    p.decks_failed
                """,
                (fmt,),
            ).fetchone()
        if row is None:
            return None
        return FormatCardPoolSummary(
            format_name=str(row[0]),
            generated_at=str(row[1]),
            source=str(row[2]),
            total_decks_analyzed=int(row[3]),
            decks_failed=int(row[4]),
            unique_cards=int(row[5]),
        )

    def list_formats(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT format_name FROM format_card_pools ORDER BY format_name ASC"
            ).fetchall()
        return [str(row[0]) for row in rows]

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


_default_repository: FormatCardPoolRepository | None = None


def get_format_card_pool_repository() -> FormatCardPoolRepository:
    global _default_repository
    if _default_repository is None:
        _default_repository = FormatCardPoolRepository()
    return _default_repository


def reset_format_card_pool_repository() -> None:
    global _default_repository
    _default_repository = None
