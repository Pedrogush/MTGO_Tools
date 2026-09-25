"""Persisting computed baselines, keyed by archetype and format.

A baseline is computed from a pool that has to be fetched, so it cannot be
recomputed in the middle of saving a deck. It is stored when the user asks for
it and read back when a new deck of that archetype is first saved, which is the
only way the root commit can be seeded without a network round trip on the save
path.

The file follows the pattern the per-deck metadata stores use (notes, outboard
and sideboard guides, ``utils/constants/storage.py``): one JSON object, read and
written whole under a path lock. It stays in ``cache/``, which those three left,
and the difference is the whole of the argument for both: a baseline is derived
from a fetched pool, so a sweep costs a recompute, while a note is something a
person typed and nothing can bring it back.

Entries are overwritten freely as the metagame moves. That does **not** re-root
any deck already created -- a deck's root is a frozen snapshot of what this held
at its creation, and :mod:`repositories.deck_vcs_repository.baseline` refuses to
change it afterwards.

Why the file says which version it is
-------------------------------------
Everything here is derived, so losing it costs a recompute -- except that a
deck's root commit is seeded from whatever this held when the deck was first
saved, so throwing the store away silently changes the root sha of every deck
created afterwards. Before the version key, forward compatibility rested
entirely on tolerance: a missing block was survivable (``_membership_from_dict``
is that, and it was already needed once), but a renamed *required* field raised
``KeyError``, which :meth:`BaselineStore.get` caught and reported as "no stored
baseline". A format change would therefore have discarded every stored baseline
without saying anything.

So the document names its version, and a version this build does not understand
is discarded *deliberately and out loud* rather than by accident. The rejected
alternatives: reading a future file anyway is the ``KeyError``-into-silence path
this exists to remove, and refusing to save over one leaves a user who moved
back to an older build with a feature that can never work again. A cache that
can be recomputed is the right thing to spend here; a silence is not.
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
    ExcludedDeck,
    FlexCandidate,
    PoolMembership,
    ZoneShape,
)
from utils.atomic_io import atomic_write_json, locked_path

#: The schema this build reads and writes. Bump it when a stored field is
#: renamed, removed, or changes meaning -- not when one is added, which the
#: readers below already tolerate.
SCHEMA_VERSION = 1

#: Where the entries live inside the document. Before the version key the
#: entries *were* the document; :func:`_entries_of` still reads that shape.
BASELINES_FIELD = "baselines"

VERSION_FIELD = "version"


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
        "main": {"size": baseline.main.size, "fixed": baseline.main.fixed},
        "sideboard": {"size": baseline.sideboard.size, "fixed": baseline.sideboard.fixed},
        "sources": list(baseline.sources),
        "membership": {
            "kept_indices": list(baseline.membership.kept_indices),
            "scores": list(baseline.membership.scores),
            "threshold": baseline.membership.threshold,
            "excluded": [
                {"source": deck.source, "similarity": deck.similarity}
                for deck in baseline.membership.excluded
            ],
        },
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
        membership=_membership_from_dict(data.get("membership")),
    )


def _membership_from_dict(data: dict[str, Any] | None) -> PoolMembership:
    """Read back a stored membership, tolerating entries written without one."""
    if not data:
        return PoolMembership()
    return PoolMembership(
        kept_indices=tuple(int(index) for index in data.get("kept_indices", ())),
        excluded=tuple(
            ExcludedDeck(source=str(deck["source"]), similarity=float(deck["similarity"]))
            for deck in data.get("excluded", ())
        ),
        scores=tuple(float(score) for score in data.get("scores", ())),
        threshold=float(data.get("threshold", 0.0)),
    )


class BaselineStore:
    """Read/write the computed-baseline JSON store."""

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            from utils.constants import ARCHETYPE_BASELINE_STORE

            path = Path(ARCHETYPE_BASELINE_STORE)
        self.path = Path(path)

    def load_all(self) -> dict[str, Any]:
        """Every stored entry, or nothing if this build cannot read the file."""
        return self._entries_of(self._read_document())

    def _read_document(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            with locked_path(self.path):
                with self.path.open("r", encoding="utf-8") as fh:
                    return dict(json.load(fh))
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            logger.warning(f"Failed to load {self.path}: {exc}")
            return {}

    def _entries_of(self, document: dict[str, Any]) -> dict[str, Any]:
        """The entries inside *document*, if this build understands its version.

        A document with no version is the pre-versioning layout, where the
        entries were the document itself. Its shape is the one this build still
        reads, so it is adopted rather than discarded; the next save rewrites it
        with a version.
        """
        if not document:
            return {}

        raw_version = document.get(VERSION_FIELD)
        if raw_version is None:
            return {key: value for key, value in document.items() if key != VERSION_FIELD}

        try:
            version = int(raw_version)
        except (TypeError, ValueError):
            version = -1

        if version != SCHEMA_VERSION:
            # Said out loud, because the cost is not the recompute: a deck's
            # root commit is seeded from this store, so every deck created from
            # here on roots differently from the ones created before.
            logger.warning(
                f"Ignoring {self.path}: it is schema version {raw_version!r} and this build "
                f"reads version {SCHEMA_VERSION}. Stored archetype baselines will be "
                "recomputed and the file rewritten on the next save."
            )
            return {}

        entries = document.get(BASELINES_FIELD)
        return dict(entries) if isinstance(entries, dict) else {}

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
            entries = self.load_all()
            entries[key] = baseline_to_dict(baseline)
            data = {VERSION_FIELD: SCHEMA_VERSION, BASELINES_FIELD: entries}
            try:
                atomic_write_json(self.path, data, indent=2)
            except OSError as exc:
                logger.error(f"Failed to save {self.path}: {exc}")
                return
        logger.info(f"Archetype baseline stored: {key} ({baseline.pool_size} decks)")

    def keys(self) -> list[str]:
        return sorted(self.load_all())
