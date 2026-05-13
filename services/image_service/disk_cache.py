"""On-disk card image cache: SQLite metadata + filesystem image files."""

from __future__ import annotations

import sqlite3
import threading
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from services.image_service.path_resolver import (
    build_path_roots,
    resolve_stored_path,
)
from services.image_service.schemas import (
    IMAGE_CACHE_DIR,
    IMAGE_DB_PATH,
    IMAGE_SIZES,
    UTC,
)
from utils.constants import SQLITE_CONNECTION_TIMEOUT_SECONDS
from utils.perf import timed


def _strip_accents(text: str) -> str:
    """Return *text* with combining diacritical marks removed (e.g. ó → o)."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    ).lower()


class CardImageCache:
    """Manages local card image cache with SQLite database."""

    def __init__(self, cache_dir: Path = IMAGE_CACHE_DIR, db_path: Path = IMAGE_DB_PATH):
        self.cache_dir = Path(cache_dir)
        self.db_path = Path(db_path)
        self._ensure_directories()
        self.cache_dir = self.cache_dir.resolve()
        self.db_path = self.db_path.resolve()
        self._path_roots = build_path_roots(self.cache_dir)
        self._init_database()
        self._path_cache: dict[tuple[str, str], Path | None] = {}
        self._path_cache_lock: threading.Lock = threading.Lock()

    def _ensure_directories(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        for size in IMAGE_SIZES.values():
            (self.cache_dir / size).mkdir(exist_ok=True)

    def _init_database(self) -> None:
        with sqlite3.connect(self.db_path, timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS) as conn:
            self._create_schema(conn)
            self._ensure_face_index_support(conn)
            conn.commit()

    def _create_schema(self, conn: sqlite3.Connection) -> None:
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

    def _resolve_path(self, stored_path: str) -> Path:
        return resolve_stored_path(stored_path, self.cache_dir, self._path_roots)

    @timed
    def get_image_path(self, card_name: str, size: str = "normal") -> Path | None:
        key = (card_name.lower(), size)
        with self._path_cache_lock:
            if key in self._path_cache:
                return self._path_cache[key]
        result = self._get_image_path_from_db(card_name, size)
        with self._path_cache_lock:
            # Only cache positive hits; None means "not yet downloaded"
            # and would suppress future availability after a download.
            if result is not None:
                self._path_cache[key] = result
        return result

    def _get_image_path_from_db(self, card_name: str, size: str) -> Path | None:
        with sqlite3.connect(self.db_path, timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS) as conn:
            cursor = conn.execute(
                """
                SELECT file_path
                FROM card_images
                WHERE LOWER(name) = LOWER(?) AND image_size = ?
                ORDER BY face_index
                LIMIT 1
                """,
                (card_name, size),
            )
            row = cursor.fetchone()
            if row:
                path = self._resolve_path(row[0])
                if path.exists():
                    return path

            alias_path = self._lookup_double_faced_alias(conn, card_name, size)
            if alias_path:
                return alias_path

            # Fallback: accent-insensitive lookup for cards like "Lórien Revealed"
            # stored under their accented Scryfall name but requested without accents
            # (or vice-versa).  SQLite's LOWER() does not strip combining characters,
            # so we register a custom scalar and compare normalised forms.
            conn.create_function("strip_accents", 1, _strip_accents)
            cursor = conn.execute(
                """
                SELECT file_path
                FROM card_images
                WHERE strip_accents(name) = ? AND image_size = ?
                ORDER BY face_index
                LIMIT 1
                """,
                (_strip_accents(card_name), size),
            )
            row = cursor.fetchone()
            if row:
                path = self._resolve_path(row[0])
                if path.exists():
                    return path
        return None

    def _lookup_double_faced_alias(
        self, conn: sqlite3.Connection, card_name: str, size: str
    ) -> Path | None:
        alias = (card_name or "").strip()
        if not alias or "//" in alias:
            return None

        alias_lower = alias.lower()
        patterns = (
            f"{alias_lower} // %",
            f"% // {alias_lower}",
        )

        for pattern in patterns:
            cursor = conn.execute(
                """
                SELECT file_path
                FROM card_images
                WHERE LOWER(name) LIKE ? AND image_size = ?
                ORDER BY face_index
                LIMIT 1
                """,
                (pattern, size),
            )
            row = cursor.fetchone()
            if row:
                path = self._resolve_path(row[0])
                if path.exists():
                    return path
        return None

    def get_image_path_for_printing(
        self, card_name: str, set_code: str, size: str = "normal"
    ) -> Path | None:
        if not set_code:
            return self.get_image_path(card_name, size)
        with sqlite3.connect(self.db_path, timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS) as conn:
            cursor = conn.execute(
                """
                SELECT file_path
                FROM card_images
                WHERE LOWER(name) = LOWER(?) AND LOWER(set_code) = LOWER(?) AND image_size = ?
                ORDER BY face_index
                LIMIT 1
                """,
                (card_name, set_code, size),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._resolve_path(row[0])

    def get_image_by_uuid(
        self, uuid: str, size: str = "normal", face_index: int | None = 0
    ) -> Path | None:
        query = "SELECT file_path FROM card_images WHERE uuid = ? AND image_size = ? ORDER BY face_index"
        params: tuple[object, ...]
        if face_index is None:
            params = (uuid, size)
        else:
            query = "SELECT file_path FROM card_images WHERE uuid = ? AND face_index = ? AND image_size = ?"
            params = (uuid, face_index, size)

        with sqlite3.connect(self.db_path, timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS) as conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            if row:
                path = self._resolve_path(row[0])
                if path.exists():
                    return path
        return None

    def get_image_paths_by_uuid(self, uuid: str, size: str = "normal") -> list[Path]:
        with sqlite3.connect(self.db_path, timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS) as conn:
            rows = conn.execute(
                """
                SELECT face_index, file_path
                FROM card_images
                WHERE uuid = ? AND image_size = ? AND face_index >= 0
                ORDER BY face_index
                """,
                (uuid, size),
            ).fetchall()
        paths: list[Path] = []
        for _, file_path in rows:
            path = self._resolve_path(file_path)
            if path.exists():
                paths.append(path)
        return paths

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
        file_path_str = str(Path(file_path).resolve())

        with sqlite3.connect(self.db_path, timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS) as conn:
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

        key = (name.lower(), image_size)
        with self._path_cache_lock:
            self._path_cache.pop(key, None)

    def get_cache_stats(self) -> dict[str, Any]:
        with sqlite3.connect(self.db_path, timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS) as conn:
            total = conn.execute("SELECT COUNT(DISTINCT uuid) FROM card_images").fetchone()[0]
            by_size = {}
            for size in IMAGE_SIZES.values():
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

    def is_cached(self, uuid: str, size: str = "normal", face_index: int | None = 0) -> bool:
        return self.get_image_by_uuid(uuid, size, face_index=face_index) is not None


__all__ = ["CardImageCache", "_strip_accents"]
