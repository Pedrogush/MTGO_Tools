"""Persisting computed baselines, keyed by archetype and format.

A baseline is computed from a pool that has to be fetched, so it cannot be
recomputed in the middle of saving a deck. It is stored when the user asks for
it and read back when a new deck of that archetype is first saved, which is the
only way the root commit can be seeded without a network round trip on the save
path.

The file follows the pattern the deck repository already uses for notes,
outboard and sideboard guides (:mod:`repositories.deck_repository.metadata_store`):
one JSON object in ``cache/``, read and written whole under a path lock.

Entries are overwritten freely as the metagame moves. That does **not** re-root
any deck already created -- a deck's root is a frozen snapshot of what this held
at its creation, and :mod:`repositories.deck_vcs_repository.baseline` refuses to
change it afterwards.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from services.archetype_baseline_service.models import (
    ArchetypeBaseline,
    BaselineCard,
    CardFrequency,
    CardRole,
    FlexCandidate,
    ZoneShape,
)
from utils.atomic_io import atomic_write_json, locked_path


def baseline_key(archetype: str, mtg_format: str) -> str:
    """The store key for one archetype in one format."""
    return f"{mtg_format.strip().lower()}::{archetype.strip().lower()}"


def _frequency_to_dict(frequency: CardFrequency) -> dict[str, Any]:
    return {
        "name": frequency.name,
        "is_sideboard": frequency.is_sideboard,
        "decks_with": frequency.decks_with,
        "pool_size": frequency.pool_size,
        # JSON object keys must be strings; counts are read back as floats.
        "counts": {str(count): decks for count, decks in frequency.counts.items()},
    }


def _frequency_from_dict(data: dict[str, Any]) -> CardFrequency:
    return CardFrequency(
        name=data["name"],
        is_sideboard=bool(data["is_sideboard"]),
        decks_with=int(data["decks_with"]),
        pool_size=int(data["pool_size"]),
        counts={float(count): int(decks) for count, decks in data.get("counts", {}).items()},
    )


def baseline_to_dict(baseline: ArchetypeBaseline) -> dict[str, Any]:
    return {
        "archetype": baseline.archetype,
        "mtg_format": baseline.mtg_format,
        "pool_size": baseline.pool_size,
        "threshold": baseline.threshold,
        "main": {"size": baseline.main.size, "fixed": baseline.main.fixed},
        "sideboard": {"size": baseline.sideboard.size, "fixed": baseline.sideboard.fixed},
        "sources": list(baseline.sources),
        "cards": [
            {
                "name": card.name,
                "is_sideboard": card.is_sideboard,
                "role": card.role.value,
                "fixed_count": card.fixed_count,
                "frequency": _frequency_to_dict(card.frequency),
            }
            for card in baseline.cards
        ],
        "flex_candidates": [
            {
                "name": candidate.name,
                "is_sideboard": candidate.is_sideboard,
                "play_rate": candidate.play_rate,
                "average_count": candidate.average_count,
                "above_floor": candidate.above_floor,
            }
            for candidate in baseline.flex_candidates
        ],
    }


def baseline_from_dict(data: dict[str, Any]) -> ArchetypeBaseline:
    return ArchetypeBaseline(
        archetype=data["archetype"],
        mtg_format=data["mtg_format"],
        pool_size=int(data["pool_size"]),
        threshold=float(data["threshold"]),
        cards=tuple(
            BaselineCard(
                name=card["name"],
                is_sideboard=bool(card["is_sideboard"]),
                role=CardRole(card["role"]),
                fixed_count=float(card["fixed_count"]),
                frequency=_frequency_from_dict(card["frequency"]),
            )
            for card in data.get("cards", [])
        ),
        flex_candidates=tuple(
            FlexCandidate(
                name=candidate["name"],
                is_sideboard=bool(candidate["is_sideboard"]),
                play_rate=float(candidate["play_rate"]),
                average_count=float(candidate["average_count"]),
                above_floor=bool(candidate["above_floor"]),
            )
            for candidate in data.get("flex_candidates", [])
        ),
        main=ZoneShape(
            size=float(data["main"]["size"]),
            fixed=float(data["main"]["fixed"]),
        ),
        sideboard=ZoneShape(
            size=float(data["sideboard"]["size"]),
            fixed=float(data["sideboard"]["fixed"]),
        ),
        sources=tuple(data.get("sources", ())),
    )


class BaselineStore:
    """Read/write the computed-baseline JSON store."""

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            from utils.constants import ARCHETYPE_BASELINE_STORE

            path = Path(ARCHETYPE_BASELINE_STORE)
        self.path = Path(path)

    def load_all(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            with locked_path(self.path):
                with self.path.open("r", encoding="utf-8") as fh:
                    return dict(json.load(fh))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Failed to load {self.path}: {exc}")
            return {}

    def get(self, archetype: str, mtg_format: str) -> ArchetypeBaseline | None:
        entry = self.load_all().get(baseline_key(archetype, mtg_format))
        if not entry:
            return None
        try:
            return baseline_from_dict(entry)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(f"Stored baseline for {archetype}/{mtg_format} unreadable: {exc}")
            return None

    def save(self, baseline: ArchetypeBaseline) -> None:
        key = baseline_key(baseline.archetype, baseline.mtg_format)
        with locked_path(self.path):
            data = self.load_all()
            data[key] = baseline_to_dict(baseline)
            try:
                atomic_write_json(self.path, data, indent=2)
            except OSError as exc:
                logger.error(f"Failed to save {self.path}: {exc}")
                return
        logger.info(f"Archetype baseline stored: {key} ({baseline.pool_size} decks)")

    def keys(self) -> list[str]:
        return sorted(self.load_all())
