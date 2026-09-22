"""SQLite CRUD operations for saved decks.

Saved decks live in a single local SQLite database under ``cache/`` alongside
the other SQLite-backed caches (deck text, format card pool, radar, images).
This replaces the previous MongoDB backend so optional deck persistence never
blocks on an external server's connection timeout.
"""

from __future__ import annotations

import json
import os
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
        # Added for #1034: the file a row was saved to, so loading that file back
        # can find the format and archetype recorded with it. Databases created
        # before the column existed gain it here, in place.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(decks)")}
        if "file_path" not in columns:
            conn.execute("ALTER TABLE decks ADD COLUMN file_path TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_decks_file_path ON decks(file_path)")
        # The deck's stable id -- what its version history is keyed by, and the
        # one attribute of a deck that survives a rename. Spelled the same as
        # ``services.deck_identity.DECK_ID_KEY`` so a row comes out of here
        # already carrying it; the column is this layer's, the meaning is that
        # module's. Rows written before the column existed gain it here, empty,
        # and their deck acquires an id on its next save.
        if "deck_uuid" not in columns:
            conn.execute("ALTER TABLE decks ADD COLUMN deck_uuid TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_decks_deck_uuid ON decks(deck_uuid)")
        conn.commit()

    @staticmethod
    def _normalize_file_path(file_path: str | Path) -> str:
        """One spelling per file: absolute, and case-folded the way Windows compares."""
        return os.path.normcase(os.path.abspath(os.fspath(file_path)))

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
        file_path: str | Path | None = None,
        deck_uuid: str | None = None,
    ):
        """Insert a saved deck, or refresh the row already recorded for this deck.

        A deck re-saved replaces its own row instead of adding a second one, so
        one deck maps to exactly one format and archetype. Which row that is, is
        answered by ``deck_uuid`` first and the file only after: a rename writes
        a *new* file, and matching on the file alone would leave the renamed
        deck with two rows -- one of them pointing at a name the user has
        already moved on from.
        """
        normalized_path = self._normalize_file_path(file_path) if file_path else None
        now = datetime.now().isoformat()
        with self._connect() as conn:
            existing = None
            if deck_uuid:
                existing = conn.execute(
                    "SELECT id FROM decks WHERE deck_uuid = ? ORDER BY id DESC LIMIT 1",
                    (deck_uuid,),
                ).fetchone()
            if existing is None and normalized_path is not None:
                existing = conn.execute(
                    "SELECT id FROM decks WHERE file_path = ? ORDER BY id DESC LIMIT 1",
                    (normalized_path,),
                ).fetchone()
            if existing is not None:
                deck_id = existing["id"]
                conn.execute(
                    """
                    UPDATE decks
                    SET name = ?, content = ?, format = ?, archetype = ?, player = ?,
                        source = ?, date_modified = ?, metadata = ?,
                        -- COALESCE, not assignment: a save that was given
                        -- neither must not blank out what the row already
                        -- holds. A rename does supply a new file and so
                        -- repoints the row it matched by deck_uuid.
                        file_path = COALESCE(?, file_path),
                        deck_uuid = COALESCE(?, deck_uuid)
                    WHERE id = ?
                    """,
                    (
                        deck_name,
                        deck_content,
                        format_type,
                        archetype,
                        player,
                        source,
                        now,
                        json.dumps(metadata or {}),
                        normalized_path,
                        deck_uuid or None,
                        deck_id,
                    ),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO decks
                        (name, content, format, archetype, player, source, date_saved,
                         metadata, file_path, deck_uuid)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        deck_name,
                        deck_content,
                        format_type,
                        archetype,
                        player,
                        source,
                        now,
                        json.dumps(metadata or {}),
                        normalized_path,
                        deck_uuid or None,
                    ),
                )
                deck_id = cursor.lastrowid
            conn.commit()

        logger.info(f"Saved deck '{deck_name}' to database with ID: {deck_id}")
        return deck_id

    def find_saved_deck(
        self,
        file_path: str | Path | None = None,
        deck_content: str | None = None,
    ) -> dict | None:
        """The saved-deck record for a deck file being loaded, or ``None``.

        Matched by the file's path first. A file moved or copied since it was
        saved no longer matches by path, so the deck text is the fallback: the
        most recent record holding the same list.
        """
        with self._connect() as conn:
            row = None
            if file_path:
                row = conn.execute(
                    "SELECT * FROM decks WHERE file_path = ? ORDER BY id DESC LIMIT 1",
                    (self._normalize_file_path(file_path),),
                ).fetchone()
            if row is None and deck_content and deck_content.strip():
                text = deck_content.replace("\r\n", "\n")
                row = conn.execute(
                    "SELECT * FROM decks WHERE content IN (?, ?) ORDER BY id DESC LIMIT 1",
                    (text, text.strip()),
                ).fetchone()
        return self._row_to_deck(row) if row is not None else None

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
                # sort_column is whitelisted (allowed_sort) and the WHERE
                # clauses bind every user value via ? placeholders in `params`.
                f"SELECT * FROM decks{where} ORDER BY {sort_column} DESC",  # nosec B608
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
                # assignments are fixed "col = ?" fragments and every value
                # (including deck_id) is bound via ? placeholders in `params`.
                f"UPDATE decks SET {', '.join(assignments)} WHERE id = ?",  # nosec B608
                params,
            )
            conn.commit()
            modified = cursor.rowcount

        if modified > 0:
            logger.info(f"Updated deck with ID: {deck_id}")
            return True

        logger.warning(f"Deck with ID {deck_id} not found or no changes made")
        return False
