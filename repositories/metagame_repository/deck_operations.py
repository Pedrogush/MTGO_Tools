"""Deck-list resolution, cached-deck aggregation, and deck-text download."""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

import repositories.metagame_repository as _pkg
from repositories.metagame_repository.date_utils import _parse_deck_date
from utils.atomic_io import locked_path


class DeckOperationsMixin:
    """Per-archetype deck fetching, aggregated listings, and deck-text download."""

    def get_decks_for_archetype(
        self,
        archetype: dict[str, Any],
        force_refresh: bool = False,
        source_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        # Support both 'href' (from get_archetypes) and 'url' for compatibility
        archetype_href = archetype.get("href") or archetype.get("url", "")
        archetype_name = archetype.get("name", "Unknown")

        if not force_refresh:
            cached = self._load_cached_decks(archetype_href)
            if cached is not None:
                logger.debug(f"Using cached decks for {archetype_name}")
                return self._sort_decks_by_date(
                    self._filter_decks_by_source(cached, source_filter)
                )

        logger.info(f"Fetching fresh decks for {archetype_name}")
        try:
            # Dynamic lookup — see archetype_resolution.py for the rationale.
            decks = _pkg.get_archetype_decks(archetype_href)
            # Preserve any MTGO-sourced entries hydrated from the remote bundle so
            # a live MTGGoldfish refresh does not evict them from the cache.
            existing = self._load_cached_decks(archetype_href, max_age=None) or []
            bundle_mtgo = [d for d in existing if d.get("source") == "mtgo"]
            merged = decks + bundle_mtgo
            self._save_cached_decks(archetype_href, merged)
            return self._sort_decks_by_date(self._filter_decks_by_source(merged, source_filter))
        except Exception as exc:
            logger.error(f"Failed to fetch decks for {archetype_name}: {exc}")
            cached = self._load_cached_decks(archetype_href, max_age=None)
            if cached:
                logger.warning(f"Returning stale cached decks for {archetype_name}")
                return self._sort_decks_by_date(
                    self._filter_decks_by_source(cached, source_filter)
                )
            raise

    def get_all_cached_decks(
        self,
        source_filter: str | None = None,
        mtg_format: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.archetype_decks_cache_file.exists():
            return []
        try:
            with locked_path(self.archetype_decks_cache_file):
                with self.archetype_decks_cache_file.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
        except json.JSONDecodeError as exc:
            logger.warning(f"Cached deck list invalid: {exc}")
            return []
        format_key = mtg_format.lower() if mtg_format else None
        # Archetype hrefs (used as cache keys) are prefixed with the format
        # slug, e.g. "modern-izzet-cauldron". Match the format as a whole word
        # anywhere in the event string too, so paper scrapes like "4 Torneio
        # Super Modern" or "Charlotte Legacy League" (whose slugs predate
        # format prefixing — "amulet-titan", "tron") are classified correctly
        # alongside MTGGoldfish's "Modern Challenge …".
        event_format_re = (
            re.compile(rf"\b{re.escape(format_key)}\b", re.IGNORECASE) if format_key else None
        )
        all_decks: list[dict[str, Any]] = []
        for slug, entry in data.items():
            items = entry.get("items", [])
            if format_key:
                slug_matches = slug.startswith(f"{format_key}-") or slug == format_key
                items = [
                    deck
                    for deck in items
                    if slug_matches
                    or (event_format_re and event_format_re.search(deck.get("event", "")))
                ]
            filtered = self._filter_decks_by_source(items, source_filter)
            all_decks.extend(filtered)
        # Deduplicate by deck number
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for deck in all_decks:
            key = deck.get("number") or deck.get("href", "")
            if key and key not in seen:
                seen.add(key)
                unique.append(deck)
            elif not key:
                unique.append(deck)
        unique.sort(key=lambda d: _parse_deck_date(d.get("date", "")), reverse=True)
        return unique

    def download_deck_content(self, deck: dict[str, Any], source_filter: str | None = None) -> str:
        deck_name = deck.get("name", "Unknown")
        deck_number = deck.get("number", "")

        if not deck_number:
            raise ValueError(f"Deck {deck_name} has no 'number' field")

        logger.info(f"Downloading deck: {deck_name}")
        try:
            # fetch_deck_text handles caching and returns the text directly,
            # avoiding a write-to-file / read-from-file roundtrip.
            deck_content = _pkg.fetch_deck_text(deck_number, source_filter=source_filter)
            return deck_content
        except Exception as exc:
            logger.error(f"Failed to download deck {deck_name}: {exc}")
            raise
