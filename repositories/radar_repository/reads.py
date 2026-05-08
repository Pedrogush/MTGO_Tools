"""Read-side queries for :class:`RadarRepository`."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from repositories.radar_repository.models import (
    CardAggregateStats,
    StoredRadar,
    StoredRadarCard,
)

if TYPE_CHECKING:
    from repositories.radar_repository.protocol import RadarRepositoryProto

    _Base = RadarRepositoryProto
else:
    _Base = object


class ReadsMixin(_Base):
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

    def get_total_decks(self, format_name: str) -> int:
        """Sum of analyzed decks across every archetype radar in a format."""
        fmt = format_name.strip().lower()
        if not fmt:
            return 0
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(total_decks_analyzed), 0)
                FROM radars
                WHERE format_name = ?
                """,
                (fmt,),
            ).fetchone()
        return int(row[0]) if row else 0

    def get_card_aggregates(
        self, format_name: str, card_names: list[str]
    ) -> dict[str, CardAggregateStats]:
        """Aggregate per-card mb/sb totals across all archetypes in a format.

        ``appearances`` rolls up to "decks containing this card" and
        ``total_copies`` to "total copies played" for the requested zone, since
        each deck belongs to a single archetype in the snapshot. Cards with no
        appearances at all are still returned as zero-filled entries so callers
        can render a stable row.
        """
        fmt = format_name.strip().lower()
        names = [name for name in (str(n).strip() for n in card_names) if name]
        if not fmt or not names:
            return {}

        results: dict[str, CardAggregateStats] = {
            name: CardAggregateStats(
                card_name=name,
                format_name=fmt,
                mainboard_archetypes=0,
                sideboard_archetypes=0,
                mainboard_copies=0,
                sideboard_copies=0,
                mainboard_appearances=0,
                sideboard_appearances=0,
            )
            for name in names
        }

        placeholders = ",".join("?" for _ in names)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    card_name,
                    zone,
                    COUNT(DISTINCT archetype_href) AS archetype_count,
                    COALESCE(SUM(total_copies), 0) AS copies,
                    COALESCE(SUM(appearances), 0) AS appearances
                FROM radar_cards
                WHERE format_name = ?
                  AND appearances > 0
                  AND card_name IN ({placeholders})
                GROUP BY card_name, zone
                """,
                (fmt, *names),
            ).fetchall()

        for row in rows:
            name = str(row[0])
            zone = str(row[1])
            current = results.get(name)
            if current is None:
                continue
            if zone == "sideboard":
                results[name] = CardAggregateStats(
                    card_name=current.card_name,
                    format_name=current.format_name,
                    mainboard_archetypes=current.mainboard_archetypes,
                    sideboard_archetypes=int(row[2]),
                    mainboard_copies=current.mainboard_copies,
                    sideboard_copies=int(row[3]),
                    mainboard_appearances=current.mainboard_appearances,
                    sideboard_appearances=int(row[4]),
                )
            else:
                results[name] = CardAggregateStats(
                    card_name=current.card_name,
                    format_name=current.format_name,
                    mainboard_archetypes=int(row[2]),
                    sideboard_archetypes=current.sideboard_archetypes,
                    mainboard_copies=int(row[3]),
                    sideboard_copies=current.sideboard_copies,
                    mainboard_appearances=int(row[4]),
                    sideboard_appearances=current.sideboard_appearances,
                )
        return results

    def get_formats_for_cards(self, card_names: list[str]) -> dict[str, list[str]]:
        """Map card name → sorted list of formats whose radars include that card.

        "Effective legality" — i.e., where the card actually shows up in the
        cached metagame snapshots, regardless of rules-text legality. A card
        that only appears as a sideboard tech in one archetype is still
        considered to "appear" in that format.
        """
        names = [name for name in (str(n).strip() for n in card_names) if name]
        if not names:
            return {}
        placeholders = ",".join("?" for _ in names)
        results: dict[str, list[str]] = {name: [] for name in names}
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT card_name, format_name
                FROM radar_cards
                WHERE appearances > 0
                  AND card_name IN ({placeholders})
                ORDER BY card_name ASC, format_name ASC
                """,
                tuple(names),
            ).fetchall()
        for row in rows:
            name = str(row[0])
            fmt = str(row[1])
            bucket = results.get(name)
            if bucket is not None:
                bucket.append(fmt)
        return results
