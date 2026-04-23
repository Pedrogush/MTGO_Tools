"""Read-side queries for :class:`RadarRepository`."""

from __future__ import annotations

import json

from repositories.radar_repository.models import StoredRadar, StoredRadarCard


class ReadsMixin:
    """Snapshot lookup and reconstruction from rows into dataclasses."""

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
