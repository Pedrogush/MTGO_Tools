"""Snapshot write paths for :class:`RadarRepository`."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from repositories.radar_repository.protocol import RadarRepositoryProto

    _Base = RadarRepositoryProto
else:
    _Base = object


class WritesMixin(_Base):
    """Bulk and per-archetype snapshot replacement."""

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
