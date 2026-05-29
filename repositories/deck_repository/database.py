"""SQLite CRUD operations for saved decks.

Saved decks live in a single local SQLite database under ``cache/`` alongside
the other SQLite-backed caches (deck text, format card pool, radar, images).
This replaces the previous MongoDB backend so optional deck persistence never
blocks on an external server's connection timeout.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from utils.constants import (
    SAVED_DECKS_DB_FILE,
    SQLITE_BUSY_TIMEOUT_MS,
    SQLITE_CONNECTION_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    from repositories.deck_repository.protocol import DeckRepositoryProto

    _Base = DeckRepositoryProto
else:
    _Base = object


class DatabaseMixin(_Base):
    """SQLite persistence for user-saved decks."""

    def _get_db_path(self) -> Path:
        if self._db_path is None:
            self._db_path = SAVED_DECKS_DB_FILE
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        db_path = self._get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        self._ensure_schema(conn)
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS decks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                format TEXT,
                archetype TEXT,
                player TEXT,
                source TEXT NOT NULL DEFAULT 'manual',
                date_saved TEXT NOT NULL,
                date_modified TEXT,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
            """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_decks_format ON decks(format)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_decks_archetype ON decks(archetype)")
        conn.commit()

    @staticmethod
    def _row_to_deck(row: sqlite3.Row) -> dict:
        deck = dict(row)
        try:
            deck["metadata"] = json.loads(deck.get("metadata") or "{}")
        except (json.JSONDecodeError, TypeError):
            deck["metadata"] = {}
        deck["_id"] = deck["id"]
        return deck

    def save_to_db(
        self,
        deck_name: str,
        deck_content: str,
        format_type: str | None = None,
        archetype: str | None = None,
        player: str | None = None,
        source: str = "manual",
        metadata: dict | None = None,
    ):
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO decks
                    (name, content, format, archetype, player, source, date_saved, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    deck_name,
                    deck_content,
                    format_type,
                    archetype,
                    player,
                    source,
                    datetime.now().isoformat(),
                    json.dumps(metadata or {}),
                ),
            )
            conn.commit()
            deck_id = cursor.lastrowid

        logger.info(f"Saved deck '{deck_name}' to database with ID: {deck_id}")
        return deck_id

    def get_decks(
        self,
        format_type: str | None = None,
        archetype: str | None = None,
        sort_by: str = "date_saved",
    ) -> list[dict]:
        allowed_sort = {
            "date_saved",
            "date_modified",
            "name",
            "format",
            "archetype",
            "player",
            "source",
            "id",
        }
        sort_column = sort_by if sort_by in allowed_sort else "date_saved"

        clauses = []
        params: list = []
        if format_type:
            clauses.append("format = ?")
            params.append(format_type)
        if archetype:
            clauses.append("archetype = ?")
            params.append(archetype)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM decks{where} ORDER BY {sort_column} DESC",
                params,
            ).fetchall()

        decks = [self._row_to_deck(row) for row in rows]
        logger.debug(f"Retrieved {len(decks)} decks from database")
        return decks

    def load_from_db(self, deck_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM decks WHERE id = ?",
                (int(deck_id),),
            ).fetchone()

        if row:
            deck = self._row_to_deck(row)
            logger.debug(f"Loaded deck: {deck['name']}")
            return deck

        logger.warning(f"Deck with ID {deck_id} not found")
        return None

    def delete_from_db(self, deck_id) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM decks WHERE id = ?", (int(deck_id),))
            conn.commit()
            deleted = cursor.rowcount

        if deleted > 0:
            logger.info(f"Deleted deck with ID: {deck_id}")
            return True

        logger.warning(f"Deck with ID {deck_id} not found for deletion")
        return False

    def update_in_db(
        self,
        deck_id,
        deck_content: str | None = None,
        deck_name: str | None = None,
        metadata: dict | None = None,
    ) -> bool:
        deck_id = int(deck_id)

        assignments = ["date_modified = ?"]
        params: list = [datetime.now().isoformat()]

        if deck_content is not None:
            assignments.append("content = ?")
            params.append(deck_content)
        if deck_name is not None:
            assignments.append("name = ?")
            params.append(deck_name)

        with self._connect() as conn:
            if metadata is not None:
                existing = conn.execute(
                    "SELECT metadata FROM decks WHERE id = ?",
                    (deck_id,),
                ).fetchone()
                if existing:
                    try:
                        merged = json.loads(existing["metadata"] or "{}")
                    except (json.JSONDecodeError, TypeError):
                        merged = {}
                    merged.update(metadata)
                    assignments.append("metadata = ?")
                    params.append(json.dumps(merged))

            params.append(deck_id)
            cursor = conn.execute(
                f"UPDATE decks SET {', '.join(assignments)} WHERE id = ?",
                params,
            )
            conn.commit()
            modified = cursor.rowcount

        if modified > 0:
            logger.info(f"Updated deck with ID: {deck_id}")
            return True

        logger.warning(f"Deck with ID {deck_id} not found or no changes made")
        return False
