"""Archetype list / deck list / deck text hydration for the bundle snapshot client."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from loguru import logger

from utils.atomic_io import atomic_write_json, locked_path

if TYPE_CHECKING:
    from services.bundle_snapshot_client.protocol import BundleSnapshotClientProto

    _Base = BundleSnapshotClientProto
else:
    _Base = object


class ArchetypeCacheMixin(_Base):
    """Hydrate archetype-list, archetype-deck, MTGO decklist, and deck-text caches."""

    def _hydrate_archetype_lists(self, archetype_entries: list[dict[str, Any]], now: float) -> None:
        if not archetype_entries:
            return

        with locked_path(self.archetype_list_cache_file):
            existing: dict[str, Any] = {}
            if self.archetype_list_cache_file.exists():
                try:
                    existing = json.loads(
                        self.archetype_list_cache_file.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError):
                    pass

            for entry in archetype_entries:
                fmt = entry.get("format", "").lower()
                archetypes = entry.get("archetypes")
                if not fmt or not isinstance(archetypes, list):
                    continue
                existing[fmt] = {"timestamp": now, "items": archetypes}

            try:
                atomic_write_json(self.archetype_list_cache_file, existing, indent=2)
                logger.debug(f"Hydrated archetype lists for {len(archetype_entries)} format(s)")
            except OSError as exc:
                logger.warning(f"Failed to write archetype list cache: {exc}")

    def _hydrate_archetype_decks(self, deck_entries: list[dict[str, Any]], now: float) -> None:
        if not deck_entries:
            return

        with locked_path(self.archetype_decks_cache_file):
            existing: dict[str, Any] = {}
            if self.archetype_decks_cache_file.exists():
                try:
                    existing = json.loads(
                        self.archetype_decks_cache_file.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError):
                    pass

            for entry in deck_entries:
                archetype = entry.get("archetype", {})
                href = archetype.get("href", "") if isinstance(archetype, dict) else ""
                decks = entry.get("decks")
                if not href or not isinstance(decks, list):
                    continue
                existing[href] = {"timestamp": now, "items": decks}

            try:
                atomic_write_json(self.archetype_decks_cache_file, existing, indent=2)
                logger.debug(f"Hydrated deck lists for {len(deck_entries)} archetype(s)")
            except OSError as exc:
                logger.warning(f"Failed to write archetype decks cache: {exc}")

    def _hydrate_deck_texts(self, deck_texts: list[tuple[str, str, str]]) -> int:
        """Insert deck texts into the SQLite deck text cache.

        Uses INSERT OR IGNORE so already-cached entries are preserved.
        """
        if not deck_texts:
            return 0
        try:
            from utils.deck_text_cache import get_deck_cache

            inserted = get_deck_cache().bulk_set(deck_texts, skip_existing=True)
            logger.debug(f"Hydrated {inserted}/{len(deck_texts)} deck texts into SQLite cache")
            return inserted
        except Exception as exc:
            logger.warning(f"Failed to hydrate deck texts: {exc}")
            return 0

    def _hydrate_mtgo_decklists(
        self,
        mtgo_decklist_entries: list[dict[str, Any]],
        archetype_entries: list[dict[str, Any]],
        now: float,
    ) -> int:
        """Merge MTGO event decklists from bundle into the archetype deck cache."""
        if not mtgo_decklist_entries:
            return 0

        name_to_href: dict[str, dict[str, str]] = {}
        for entry in archetype_entries:
            fmt = entry.get("format", "").lower()
            for arch in entry.get("archetypes", []):
                name = arch.get("name", "")
                href = arch.get("href", "")
                if name and href:
                    name_to_href.setdefault(fmt, {})[name] = href

        deck_texts: list[tuple[str, str, str]] = []
        decks_by_href: dict[str, list[dict[str, Any]]] = {}

        for entry in mtgo_decklist_entries:
            fmt = entry.get("format", "").lower()
            fmt_lookup = name_to_href.get(fmt, {})
            for event in entry.get("events", []):
                for deck in event.get("decks", []):
                    arch_name = deck.get("archetype", "")
                    href = fmt_lookup.get(arch_name)
                    if not href:
                        continue
                    deck_id = deck.get("number", "")
                    deck_text = deck.get("deck_text", "")
                    if deck_id and deck_text:
                        deck_texts.append((deck_id, deck_text, "mtgo"))
                    date_raw = deck.get("date", "")
                    metadata: dict[str, Any] = {
                        "date": date_raw[:10] if date_raw else "",
                        "number": deck_id,
                        "player": deck.get("player", ""),
                        "event": deck.get("event", ""),
                        "result": deck.get("result", ""),
                        "name": deck.get("name", ""),
                        "source": "mtgo",
                    }
                    decks_by_href.setdefault(href, []).append(metadata)

        if not decks_by_href:
            logger.debug("No MTGO decks could be matched to known archetypes")
            return 0

        if deck_texts:
            try:
                from utils.deck_text_cache import get_deck_cache

                get_deck_cache().bulk_set(deck_texts, skip_existing=True)
            except Exception as exc:
                logger.warning(f"Failed to insert MTGO deck texts: {exc}")

        total = 0
        with locked_path(self.archetype_decks_cache_file):
            existing: dict[str, Any] = {}
            if self.archetype_decks_cache_file.exists():
                try:
                    existing = json.loads(
                        self.archetype_decks_cache_file.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError):
                    pass

            for href, mtgo_decks in decks_by_href.items():
                existing_entry = existing.get(href, {})
                existing_items = existing_entry.get("items", [])
                goldfish_items = [d for d in existing_items if d.get("source") != "mtgo"]
                existing[href] = {
                    "timestamp": existing_entry.get("timestamp", now),
                    "items": goldfish_items + mtgo_decks,
                }
                total += len(mtgo_decks)

            try:
                atomic_write_json(self.archetype_decks_cache_file, existing, indent=2)
                logger.debug(
                    f"Merged {total} MTGO decks into {len(decks_by_href)} archetype cache entries"
                )
            except OSError as exc:
                logger.warning(f"Failed to write archetype decks cache with MTGO decks: {exc}")

        return total
