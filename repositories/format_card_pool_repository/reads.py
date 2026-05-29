"""Read-side queries for :class:`FormatCardPoolRepository`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from repositories.format_card_pool_repository.models import (
    FormatCardPoolCardTotal,
    FormatCardPoolSummary,
)

if TYPE_CHECKING:
    from repositories.format_card_pool_repository.protocol import (
        FormatCardPoolRepositoryProto,
    )

    _Base = FormatCardPoolRepositoryProto
else:
    _Base = object


class ReadsMixin(_Base):
    """Lookup, listing, and summary queries against the cached snapshots."""

    def has_format_pool(self, format_name: str) -> bool:
        fmt = format_name.strip().lower()
        if not fmt:
            return False
        with self._read_lock:
            row = (
                self._read_connection()
                .execute(
                    "SELECT 1 FROM format_card_pools WHERE format_name = ? LIMIT 1",
                    (fmt,),
                )
                .fetchone()
            )
        return row is not None

    def get_card_names(self, format_name: str) -> set[str]:
        fmt = format_name.strip().lower()
        if not fmt:
            return set()
        with self._read_lock:
            rows = (
                self._read_connection()
                .execute(
                    """
                SELECT card_name
                FROM format_card_pool_cards
                WHERE format_name = ?
                """,
                    (fmt,),
                )
                .fetchall()
            )
        return {str(row[0]) for row in rows}

    def get_card_total(self, format_name: str, card_name: str) -> int | None:
        """Return the recorded copies-played for a card, or ``None`` when the
        card isn't tracked in the snapshot for that format.

        ``0`` means "tracked, but never played in the analyzed decks"; ``None``
        means "the snapshot didn't include this card at all" — the upstream
        bundle's pool sample is a filtered subset of legal cards, so missing
        rows are normal.

        Hit on every card hover/selection, so results are memoized per
        ``(format, card)`` and the cache is cleared on snapshot writes.
        """
        fmt = format_name.strip().lower()
        if not fmt or not card_name:
            return None
        key = (fmt, card_name)
        with self._read_lock:
            cache = self._card_total_cache
            if key in cache:
                return cache[key]
            row = (
                self._read_connection()
                .execute(
                    """
                SELECT copies_played
                FROM format_card_pool_cards
                WHERE format_name = ? AND card_name = ?
                """,
                    (fmt, card_name),
                )
                .fetchone()
            )
            total = int(row[0]) if row else None
            cache[key] = total
        return total

    def get_top_cards(self, format_name: str, limit: int = 100) -> list[FormatCardPoolCardTotal]:
        fmt = format_name.strip().lower()
        if not fmt:
            return []
        limit = max(1, int(limit))
        with self._read_lock:
            rows = (
                self._read_connection()
                .execute(
                    """
                SELECT card_name, copies_played
                FROM format_card_pool_cards
                WHERE format_name = ? AND copies_played > 0
                ORDER BY copies_played DESC, card_name ASC
                LIMIT ?
                """,
                    (fmt, limit),
                )
                .fetchall()
            )
        return [
            FormatCardPoolCardTotal(card_name=row[0], copies_played=int(row[1])) for row in rows
        ]

    def get_summary(self, format_name: str) -> FormatCardPoolSummary | None:
        """Return the snapshot summary for a format.

        Hit on every card hover/selection alongside :meth:`get_card_total`, so
        the result is memoized per format and cleared on snapshot writes.
        """
        fmt = format_name.strip().lower()
        if not fmt:
            return None
        with self._read_lock:
            cache = self._summary_cache
            if fmt in cache:
                return cache[fmt]
            row = (
                self._read_connection()
                .execute(
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
                )
                .fetchone()
            )
            if row is None:
                cache[fmt] = None
                return None
            summary = FormatCardPoolSummary(
                format_name=str(row[0]),
                generated_at=str(row[1]),
                source=str(row[2]),
                total_decks_analyzed=int(row[3]),
                decks_failed=int(row[4]),
                unique_cards=int(row[5]),
            )
            cache[fmt] = summary
        return summary

    def list_formats(self) -> list[str]:
        with self._read_lock:
            rows = (
                self._read_connection()
                .execute("SELECT format_name FROM format_card_pools ORDER BY format_name ASC")
                .fetchall()
            )
        return [str(row[0]) for row in rows]
