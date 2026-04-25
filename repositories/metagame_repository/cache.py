"""JSON cache I/O and deck-list helpers for :class:`MetagameRepository`."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, Final

from loguru import logger

from repositories.metagame_repository.date_utils import _parse_deck_date
from utils.atomic_io import atomic_write_json, locked_path

if TYPE_CHECKING:
    from repositories.metagame_repository.protocol import MetagameRepositoryProto

    _Base = MetagameRepositoryProto
else:
    _Base = object

_USE_DEFAULT_MAX_AGE: Final = object()


class CacheMixin(_Base):
    """Archetype-list / archetype-decks cache read/write and filter helpers."""

    def _load_cached_archetypes(
        self, mtg_format: str, max_age: int | None | object = _USE_DEFAULT_MAX_AGE
    ) -> list[dict[str, Any]] | None:
        if max_age == -1:
            max_age = _USE_DEFAULT_MAX_AGE
        effective_max_age = self.cache_ttl if max_age is _USE_DEFAULT_MAX_AGE else max_age

        if not self.archetype_list_cache_file.exists():
            return None

        try:
            with locked_path(self.archetype_list_cache_file):
                with self.archetype_list_cache_file.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
        except json.JSONDecodeError as exc:
            logger.warning(f"Cached archetype list invalid: {exc}")
            return None

        entry = data.get(mtg_format)
        if not entry:
            return None

        if effective_max_age is not None:
            timestamp = entry.get("timestamp", 0)
            if time.time() - timestamp > effective_max_age:
                logger.debug(f"Archetype cache for {mtg_format} expired")
                return None

        return entry.get("items")

    def _save_cached_archetypes(self, mtg_format: str, items: list[dict[str, Any]]) -> None:
        with locked_path(self.archetype_list_cache_file):
            data: dict[str, Any] = {}
            if self.archetype_list_cache_file.exists():
                try:
                    with self.archetype_list_cache_file.open("r", encoding="utf-8") as fh:
                        data = json.load(fh)
                except json.JSONDecodeError as exc:
                    logger.warning(f"Archetype cache invalid, rebuilding: {exc}")

            data[mtg_format] = {"timestamp": time.time(), "items": items}

            try:
                atomic_write_json(self.archetype_list_cache_file, data, indent=2)
                logger.debug(f"Cached {len(items)} archetypes for {mtg_format}")
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(f"Failed to cache archetypes: {exc}")

    def _load_cached_decks(
        self, archetype_url: str, max_age: int | None | object = _USE_DEFAULT_MAX_AGE
    ) -> list[dict[str, Any]] | None:
        if max_age == -1:
            max_age = _USE_DEFAULT_MAX_AGE
        effective_max_age = self.cache_ttl if max_age is _USE_DEFAULT_MAX_AGE else max_age

        if not self.archetype_decks_cache_file.exists():
            return None

        try:
            with locked_path(self.archetype_decks_cache_file):
                with self.archetype_decks_cache_file.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
        except json.JSONDecodeError as exc:
            logger.warning(f"Cached deck list invalid: {exc}")
            return None

        entry = data.get(archetype_url)
        if not entry:
            return None

        if effective_max_age is not None:
            timestamp = entry.get("timestamp", 0)
            if time.time() - timestamp > effective_max_age:
                logger.debug("Deck cache for archetype expired")
                return None

        return entry.get("items")

    def _save_cached_decks(self, archetype_url: str, items: list[dict[str, Any]]) -> None:
        with locked_path(self.archetype_decks_cache_file):
            data: dict[str, Any] = {}
            if self.archetype_decks_cache_file.exists():
                try:
                    with self.archetype_decks_cache_file.open("r", encoding="utf-8") as fh:
                        data = json.load(fh)
                except json.JSONDecodeError as exc:
                    logger.warning(f"Deck cache invalid, rebuilding: {exc}")

            data[archetype_url] = {"timestamp": time.time(), "items": items}

            try:
                atomic_write_json(self.archetype_decks_cache_file, data, indent=2)
                logger.debug(f"Cached {len(items)} decks for archetype")
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(f"Failed to cache decks: {exc}")

    def _filter_decks_by_source(
        self, decks: list[dict[str, Any]], source_filter: str | None
    ) -> list[dict[str, Any]]:
        if not source_filter or source_filter == "both":
            return decks

        return [deck for deck in decks if deck.get("source") == source_filter]

    def _sort_decks_by_date(self, decks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(decks, key=lambda d: _parse_deck_date(d.get("date", "")), reverse=True)

    def clear_cache(self) -> None:
        for cache_file in [self.archetype_list_cache_file, self.archetype_decks_cache_file]:
            if cache_file.exists():
                try:
                    cache_file.unlink()
                    logger.info(f"Cleared cache: {cache_file}")
                except OSError as exc:
                    logger.warning(f"Failed to clear cache {cache_file}: {exc}")
