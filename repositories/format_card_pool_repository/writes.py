"""Snapshot write paths for :class:`FormatCardPoolRepository`."""

from __future__ import annotations

from typing import Any

from loguru import logger


class WritesMixin:
    """Bulk and per-format snapshot replacement."""

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
