"""
SQLite-based deck text cache for scalable, high-performance caching.

This module provides a robust caching layer for MTGGoldfish deck texts using SQLite,
eliminating the performance issues of large JSON files and providing instant lookups
even with millions of cached decks.
"""

import json
import sqlite3
import time
from pathlib import Path

from loguru import logger

from utils.constants import CACHE_DIR

# SQLite database location
DECK_CACHE_DB = CACHE_DIR / "deck_cache.db"


class DeckTextCache:
    """SQLite-based cache for deck text content."""

    def __init__(self, db_path: Path = DECK_CACHE_DB):
        """
        Initialize the deck text cache.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create the cache table and indexes if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            cursor = conn.cursor()

            # Enable WAL mode for better concurrent access
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")  # 30 second timeout

            # Create main cache table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS deck_cache (
                    deck_number TEXT PRIMARY KEY,
                    deck_text TEXT NOT NULL,
                    source TEXT DEFAULT 'mtggoldfish',
                    cached_at REAL NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    last_accessed REAL NOT NULL
                )
            """)

            # Add source column to existing tables (migration)
            try:
                cursor.execute(
                    "ALTER TABLE deck_cache ADD COLUMN source TEXT DEFAULT 'mtggoldfish'"
                )
                conn.commit()
                logger.info("Added source column to deck_cache table")
            except sqlite3.OperationalError:
                # Column already exists
                pass

            # Create index on last_accessed for efficient LRU operations
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_last_accessed
                ON deck_cache(last_accessed DESC)
            """)

            # Create index on cached_at for cleanup operations
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cached_at
                ON deck_cache(cached_at)
            """)

            conn.commit()
            logger.debug(f"Deck cache schema initialized at {self.db_path}")

    def get(self, deck_number: str, source: str | None = None) -> str | None:
        """
        Get deck text from cache.

        Args:
            deck_number: Deck number/ID
            source: Optional source filter ('mtggoldfish' or 'mtgo')

        Returns:
            Deck text if found, None otherwise
        """
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                cursor = conn.cursor()

                # Get deck text and update access statistics
                if source:
                    cursor.execute(
                        """
                        SELECT deck_text FROM deck_cache
                        WHERE deck_number = ? AND source = ?
                        """,
                        (deck_number, source),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT deck_text FROM deck_cache
                        WHERE deck_number = ?
                        """,
                        (deck_number,),
                    )

                row = cursor.fetchone()

                if row:
                    deck_text = row[0]

                    # Update access statistics
                    cursor.execute(
                        """
                        UPDATE deck_cache
                        SET access_count = access_count + 1,
                            last_accessed = ?
                        WHERE deck_number = ?
                        """,
                        (time.time(), deck_number),
                    )
                    conn.commit()

                    logger.debug(f"Cache HIT for deck {deck_number}")
                    return deck_text

                logger.debug(f"Cache MISS for deck {deck_number}")
                return None

        except sqlite3.Error as exc:
            logger.error(f"Error reading from deck cache: {exc}")
            return None

    def set(self, deck_number: str, deck_text: str, source: str = "mtggoldfish") -> bool:
        """
        Store deck text in cache with retry logic for database locks.

        Args:
            deck_number: Deck number/ID
            deck_text: Deck list as text
            source: Data source ('mtggoldfish' or 'mtgo')

        Returns:
            True if successful, False otherwise
        """
        max_retries = 3
        retry_delay = 0.1  # Start with 100ms

        for attempt in range(max_retries):
            try:
                with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                    cursor = conn.cursor()

                    now = time.time()

                    # Insert or replace deck text
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO deck_cache
                        (deck_number, deck_text, source, cached_at, access_count, last_accessed)
                        VALUES (?, ?, ?, ?, COALESCE((SELECT access_count FROM deck_cache WHERE deck_number = ?), 0), ?)
                        """,
                        (deck_number, deck_text, source, now, deck_number, now),
                    )

                    conn.commit()
                    return True

            except sqlite3.OperationalError as exc:
                if "database is locked" in str(exc) and attempt < max_retries - 1:
                    logger.warning(
                        f"Database locked, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    logger.error(f"Error writing to deck cache after {attempt + 1} attempts: {exc}")
                    return False
            except sqlite3.Error as exc:
                logger.error(f"Error writing to deck cache: {exc}")
                return False

        return False

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats (total_decks, db_size_mb, oldest_entry, newest_entry)
        """
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                cursor = conn.cursor()

                # Get total count
                cursor.execute("SELECT COUNT(*) FROM deck_cache")
                total_decks = cursor.fetchone()[0]

                # Get oldest and newest entries
                cursor.execute("SELECT MIN(cached_at), MAX(cached_at) FROM deck_cache")
                oldest, newest = cursor.fetchone()

                # Get database file size
                db_size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
                db_size_mb = db_size_bytes / (1024 * 1024)

                # Get most accessed decks
                cursor.execute("""
                    SELECT deck_number, access_count
                    FROM deck_cache
                    ORDER BY access_count DESC
                    LIMIT 10
                    """)
                top_decks = cursor.fetchall()

                return {
                    "total_decks": total_decks,
                    "db_size_mb": round(db_size_mb, 2),
                    "oldest_entry": oldest,
                    "newest_entry": newest,
                    "top_accessed": top_decks,
                }

        except sqlite3.Error as exc:
            logger.error(f"Error getting cache stats: {exc}")
            return {"error": str(exc)}

    def cleanup_old_entries(self, max_age_days: int = 90) -> int:
        """
        Remove entries older than max_age_days.

        Args:
            max_age_days: Maximum age in days

        Returns:
            Number of entries deleted
        """
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)

        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                cursor = conn.cursor()

                cursor.execute(
                    "DELETE FROM deck_cache WHERE cached_at < ?",
                    (cutoff_time,),
                )

                deleted = cursor.rowcount
                conn.commit()

                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} old deck cache entries")

                return deleted

        except sqlite3.Error as exc:
            logger.error(f"Error cleaning up cache: {exc}")
            return 0

    def cleanup_lru(self, max_entries: int = 10000) -> int:
        """
        Keep only the most recently accessed entries (LRU eviction).

        Args:
            max_entries: Maximum number of entries to keep

        Returns:
            Number of entries deleted
        """
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                cursor = conn.cursor()

                # Count current entries
                cursor.execute("SELECT COUNT(*) FROM deck_cache")
                current_count = cursor.fetchone()[0]

                if current_count <= max_entries:
                    return 0

                # Delete least recently accessed entries
                cursor.execute(
                    """
                    DELETE FROM deck_cache
                    WHERE deck_number IN (
                        SELECT deck_number
                        FROM deck_cache
                        ORDER BY last_accessed ASC
                        LIMIT ?
                    )
                    """,
                    (current_count - max_entries,),
                )

                deleted = cursor.rowcount
                conn.commit()

                if deleted > 0:
                    logger.info(f"LRU cleanup removed {deleted} least-accessed deck entries")

                return deleted

        except sqlite3.Error as exc:
            logger.error(f"Error during LRU cleanup: {exc}")
            return 0

    def migrate_from_json(self, json_path: Path) -> int:
        """
        Migrate existing JSON cache to SQLite.

        Args:
            json_path: Path to existing JSON cache file

        Returns:
            Number of entries migrated
        """
        if not json_path.exists():
            logger.debug(f"No JSON cache to migrate at {json_path}")
            return 0

        try:
            with json_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)

            if not isinstance(data, dict):
                logger.warning("JSON cache format unexpected, skipping migration")
                return 0

            migrated = 0
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                cursor = conn.cursor()
                now = time.time()

                for deck_number, deck_text in data.items():
                    try:
                        cursor.execute(
                            """
                            INSERT OR IGNORE INTO deck_cache
                            (deck_number, deck_text, cached_at, access_count, last_accessed)
                            VALUES (?, ?, ?, 0, ?)
                            """,
                            (deck_number, deck_text, now, now),
                        )
                        if cursor.rowcount > 0:
                            migrated += 1
                    except sqlite3.Error as exc:
                        logger.warning(f"Failed to migrate deck {deck_number}: {exc}")
                        continue

                conn.commit()

            logger.info(f"Migrated {migrated} decks from JSON to SQLite cache")
            return migrated

        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Error migrating JSON cache: {exc}")
            return 0

    def vacuum(self) -> None:
        """Optimize database and reclaim space after deletions."""
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                conn.execute("VACUUM")
                logger.info("Database vacuumed successfully")
        except sqlite3.Error as exc:
            logger.error(f"Error vacuuming database: {exc}")

    def clear(self) -> bool:
        """
        Clear all cached entries.

        Returns:
            True if successful
        """
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                conn.execute("DELETE FROM deck_cache")
                conn.commit()
            logger.info("Deck cache cleared")
            return True
        except sqlite3.Error as exc:
            logger.error(f"Error clearing cache: {exc}")
            return False


# Global cache instance
_cache_instance: DeckTextCache | None = None


def get_deck_cache() -> DeckTextCache:
    """Get the global deck text cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = DeckTextCache()
    return _cache_instance


def reset_deck_cache() -> None:
    """Reset the global cache instance (useful for testing)."""
    global _cache_instance
    _cache_instance = None
