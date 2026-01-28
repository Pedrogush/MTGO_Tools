"""SQLite-backed persistence layer for the card image cache.

Owns schema creation, migrations, and all read/write queries against the
``card_images`` and ``bulk_data_meta`` tables.  Path resolution is the
responsibility of the caller (``CardImageCache``).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

try:  # Python 3.11+ has UTC
    from datetime import UTC
except ImportError:  # pragma: no cover - compatibility shim for Python 3.10
    UTC = timezone.utc  # noqa: UP017

# Enumeration of recognised image sizes used for per-size statistics.
_IMAGE_SIZE_KEYS = ("small", "normal", "large", "png")


class CardImageStore:
    """Low-level SQLite store for card image records and bulk-data metadata.

    All methods accept or return raw strings/tuples; path resolution and
    existence checks are handled by the calling layer.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path.resolve()
        self._init_database()

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def _init_database(self) -> None:
        """Initialize SQLite database schema."""
        with sqlite3.connect(self.db_path) as conn:
            self._create_schema(conn)
            self._ensure_face_index_support(conn)
            conn.commit()

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        """Create base tables if they do not exist."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS card_images (
                uuid TEXT NOT NULL,
                face_index INTEGER NOT NULL DEFAULT 0,
                name TEXT NOT NULL,
                set_code TEXT,
                collector_number TEXT,
                image_size TEXT NOT NULL,
                file_path TEXT NOT NULL,
                downloaded_at TEXT NOT NULL,
                scryfall_uri TEXT,
                artist TEXT,
                PRIMARY KEY (uuid, face_index, image_size)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_card_name ON card_images(name)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_set_code ON card_images(set_code)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bulk_data_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                downloaded_at TEXT NOT NULL,
                total_cards INTEGER NOT NULL,
                bulk_data_uri TEXT NOT NULL
            )
        """)

    def _ensure_face_index_support(self, conn: sqlite3.Connection) -> None:
        """Ensure the card_images table can store multiple faces per UUID."""
        info = conn.execute("PRAGMA table_info(card_images)").fetchall()
        has_face_index = any(column[1] == "face_index" for column in info)
        if has_face_index:
            return

        logger.info("Migrating card_images table to support multi-face entries")
        conn.execute("ALTER TABLE card_images RENAME TO card_images_old")
        self._create_schema(conn)
        conn.execute("""
            INSERT INTO card_images (
                uuid,
                face_index,
                name,
                set_code,
                collector_number,
                image_size,
                file_path,
                downloaded_at,
                scryfall_uri,
                artist
            )
            SELECT
                uuid,
                0,
                name,
                set_code,
                collector_number,
                image_size,
                file_path,
                downloaded_at,
                scryfall_uri,
                artist
            FROM card_images_old
        """)
        conn.execute("DROP TABLE card_images_old")

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add_image(
        self,
        uuid: str,
        name: str,
        set_code: str,
        collector_number: str,
        image_size: str,
        file_path: Path,
        scryfall_uri: str | None = None,
        artist: str | None = None,
        face_index: int = 0,
    ) -> None:
        """Persist a card-image record."""
        file_path_str = str(Path(file_path).resolve())

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO card_images
                (uuid, face_index, name, set_code, collector_number, image_size, file_path,
                 downloaded_at, scryfall_uri, artist)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    uuid,
                    face_index,
                    name,
                    set_code,
                    collector_number,
                    image_size,
                    file_path_str,
                    datetime.now(UTC).isoformat(),
                    scryfall_uri,
                    artist,
                ),
            )
            conn.commit()

    def upsert_bulk_data_meta(
        self,
        downloaded_at: str,
        total_cards: int,
        bulk_data_uri: str,
    ) -> None:
        """Insert or update the singleton bulk-data metadata row."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO bulk_data_meta (id, downloaded_at, total_cards, bulk_data_uri)
                VALUES (1, ?, ?, ?)
            """,
                (downloaded_at, total_cards, bulk_data_uri),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Read operations – card_images
    # ------------------------------------------------------------------

    def get_rows_by_name(self, card_name: str, image_size: str) -> list[tuple[str, ...]]:
        """Return (file_path,) rows matching a case-insensitive card name.

        Rows are ordered by face_index ascending so that the front face
        appears first.
        """
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT file_path
                FROM card_images
                WHERE LOWER(name) = LOWER(?) AND image_size = ?
                ORDER BY face_index
                """,
                (card_name, image_size),
            ).fetchall()
        return rows

    def get_rows_by_name_pattern(self, pattern: str, image_size: str) -> list[tuple[str, ...]]:
        """Return (file_path,) rows matching a SQL LIKE pattern on name."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT file_path
                FROM card_images
                WHERE LOWER(name) LIKE ? AND image_size = ?
                ORDER BY face_index
                LIMIT 1
                """,
                (pattern, image_size),
            ).fetchall()
        return rows

    def get_rows_by_uuid(
        self,
        uuid: str,
        image_size: str,
        face_index: int | None = 0,
    ) -> list[tuple[str, ...]]:
        """Return (file_path,) rows for a UUID, optionally filtered by face_index."""
        if face_index is None:
            rows = self._query(
                "SELECT file_path FROM card_images WHERE uuid = ? AND image_size = ? ORDER BY face_index",
                (uuid, image_size),
            )
        else:
            rows = self._query(
                "SELECT file_path FROM card_images WHERE uuid = ? AND face_index = ? AND image_size = ?",
                (uuid, face_index, image_size),
            )
        return rows

    def get_all_face_rows(self, uuid: str, image_size: str) -> list[tuple[int, str]]:
        """Return (face_index, file_path) for non-alias faces, ordered ascending."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT face_index, file_path
                FROM card_images
                WHERE uuid = ? AND image_size = ? AND face_index >= 0
                ORDER BY face_index
                """,
                (uuid, image_size),
            ).fetchall()
        return rows

    # ------------------------------------------------------------------
    # Read operations – bulk_data_meta
    # ------------------------------------------------------------------

    def get_bulk_data_record(self) -> tuple[str | None, str | None]:
        """Return (downloaded_at, bulk_data_uri) or (None, None)."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT downloaded_at, bulk_data_uri FROM bulk_data_meta WHERE id = 1"
            ).fetchone()
        if row:
            return row[0], row[1]
        return None, None

    # ------------------------------------------------------------------
    # Aggregate / statistics
    # ------------------------------------------------------------------

    def get_cache_stats(self) -> dict[str, Any]:
        """Return a statistics dictionary over the entire cache."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(DISTINCT uuid) FROM card_images").fetchone()[0]
            by_size: dict[str, int] = {}
            for size in _IMAGE_SIZE_KEYS:
                count = conn.execute(
                    "SELECT COUNT(*) FROM card_images WHERE image_size = ?", (size,)
                ).fetchone()[0]
                by_size[size] = count

            bulk_meta = conn.execute(
                "SELECT downloaded_at, total_cards FROM bulk_data_meta WHERE id = 1"
            ).fetchone()

        return {
            "unique_cards": total,
            "by_size": by_size,
            "bulk_data_date": bulk_meta[0] if bulk_meta else None,
            "bulk_total_cards": bulk_meta[1] if bulk_meta else None,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _query(self, sql: str, params: tuple[object, ...]) -> list[tuple[str, ...]]:
        """Execute a read-only query and return all rows."""
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(sql, params).fetchall()
