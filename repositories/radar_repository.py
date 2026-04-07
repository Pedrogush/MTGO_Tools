"""Repository for locally cached precomputed radar snapshots."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from utils.constants import RADAR_CACHE_DB_FILE, SQLITE_CONNECTION_TIMEOUT_SECONDS


@dataclass(frozen=True)
class StoredRadarCard:
    """One persisted radar card row."""

    card_name: str
    appearances: int
    total_copies: int
    max_copies: int
    avg_copies: float
    inclusion_rate: float
    expected_copies: float
    copy_distribution: dict[int, int]


@dataclass(frozen=True)
class StoredRadar:
    """Full persisted radar snapshot."""

    archetype_name: str
    archetype_href: str
    format_name: str
    generated_at: str
    source: str
    total_decks_analyzed: int
    decks_failed: int
    mainboard_cards: list[StoredRadarCard]
    sideboard_cards: list[StoredRadarCard]


class RadarRepository:
    """Read and write locally cached precomputed radar snapshots."""

    def __init__(self, db_path: Path = RADAR_CACHE_DB_FILE) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def replace_radar(self, entry: dict[str, Any]) -> bool:
        format_name = str(entry.get("format", "")).strip().lower()
        archetype = entry.get("archetype") or {}
        if not isinstance(archetype, dict):
            return False
        archetype_href = str(archetype.get("href", "")).strip()
        if not format_name or not archetype_href:
            return False

        card_rows: list[tuple[str, str, str, str, int, int, int, float, float, float, str]] = []
        for zone, cards in (
            ("mainboard", entry.get("mainboard_cards", []) or []),
            ("sideboard", entry.get("sideboard_cards", []) or []),
        ):
            if not isinstance(cards, list):
                continue
            for card in cards:
                if not isinstance(card, dict):
                    continue
                card_name = str(card.get("card_name", "")).strip()
                if not card_name:
                    continue
                distribution = card.get("copy_distribution", {}) or {}
                if not isinstance(distribution, dict):
                    distribution = {}
                normalized_distribution = {
                    int(key): int(value) for key, value in distribution.items() if str(key).strip()
                }
                card_rows.append(
                    (
                        format_name,
                        archetype_href,
                        zone,
                        card_name,
                        int(card.get("appearances", 0) or 0),
                        int(card.get("total_copies", 0) or 0),
                        int(card.get("max_copies", 0) or 0),
                        float(card.get("avg_copies", 0.0) or 0.0),
                        float(card.get("inclusion_rate", 0.0) or 0.0),
                        float(card.get("expected_copies", 0.0) or 0.0),
                        json.dumps(normalized_distribution, sort_keys=True),
                    )
                )

        with self._connect() as conn:
            conn.execute("BEGIN")
            conn.execute(
                "DELETE FROM radar_cards WHERE format_name = ? AND archetype_href = ?",
                (format_name, archetype_href),
            )
            conn.execute(
                "DELETE FROM radars WHERE format_name = ? AND archetype_href = ?",
                (format_name, archetype_href),
            )
            conn.execute(
                """
                INSERT INTO radars (
                    format_name,
                    archetype_href,
                    archetype_name,
                    generated_at,
                    source,
                    total_decks_analyzed,
                    decks_failed
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    format_name,
                    archetype_href,
                    str(archetype.get("name", "")).strip(),
                    str(entry.get("generated_at", "")).strip(),
                    str(entry.get("source", "")).strip(),
                    int(entry.get("total_decks_analyzed", 0) or 0),
                    int(entry.get("decks_failed", 0) or 0),
                ),
            )
            conn.executemany(
                """
                INSERT INTO radar_cards (
                    format_name,
                    archetype_href,
                    zone,
                    card_name,
                    appearances,
                    total_copies,
                    max_copies,
                    avg_copies,
                    inclusion_rate,
                    expected_copies,
                    copy_distribution_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                card_rows,
            )
            conn.commit()
        return True

    def bulk_replace(self, entries: list[dict[str, Any]]) -> int:
        replaced = 0
        for entry in entries:
            try:
                replaced += int(self.replace_radar(entry))
            except Exception as exc:
                logger.warning(f"Failed to replace radar snapshot: {exc}")
        return replaced

    def get_radar(self, format_name: str, archetype_href: str) -> StoredRadar | None:
        fmt = format_name.strip().lower()
        href = archetype_href.strip()
        if not fmt or not href:
            return None

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    archetype_name,
                    generated_at,
                    source,
                    total_decks_analyzed,
                    decks_failed
                FROM radars
                WHERE format_name = ? AND archetype_href = ?
                """,
                (fmt, href),
            ).fetchone()
            if row is None:
                return None

            card_rows = conn.execute(
                """
                SELECT
                    zone,
                    card_name,
                    appearances,
                    total_copies,
                    max_copies,
                    avg_copies,
                    inclusion_rate,
                    expected_copies,
                    copy_distribution_json
                FROM radar_cards
                WHERE format_name = ? AND archetype_href = ?
                ORDER BY
                    zone ASC,
                    expected_copies DESC,
                    inclusion_rate DESC,
                    card_name ASC
                """,
                (fmt, href),
            ).fetchall()

        mainboard_cards: list[StoredRadarCard] = []
        sideboard_cards: list[StoredRadarCard] = []
        for card_row in card_rows:
            distribution_raw = json.loads(card_row[8] or "{}")
            distribution = {int(key): int(value) for key, value in distribution_raw.items()}
            card = StoredRadarCard(
                card_name=str(card_row[1]),
                appearances=int(card_row[2]),
                total_copies=int(card_row[3]),
                max_copies=int(card_row[4]),
                avg_copies=float(card_row[5]),
                inclusion_rate=float(card_row[6]),
                expected_copies=float(card_row[7]),
                copy_distribution=distribution,
            )
            if str(card_row[0]) == "sideboard":
                sideboard_cards.append(card)
            else:
                mainboard_cards.append(card)

        return StoredRadar(
            archetype_name=str(row[0]),
            archetype_href=href,
            format_name=fmt,
            generated_at=str(row[1]),
            source=str(row[2]),
            total_decks_analyzed=int(row[3]),
            decks_failed=int(row[4]),
            mainboard_cards=mainboard_cards,
            sideboard_cards=sideboard_cards,
        )

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


_default_repository: RadarRepository | None = None


def get_radar_repository() -> RadarRepository:
    global _default_repository
    if _default_repository is None:
        _default_repository = RadarRepository()
    return _default_repository


def reset_radar_repository() -> None:
    global _default_repository
    _default_repository = None
