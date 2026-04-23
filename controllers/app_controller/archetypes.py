"""Archetype and deck-list fetch/refresh logic for :class:`AppController`."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from loguru import logger

from services.deck_workflow_service import DeckLoadScope


class ArchetypesMixin:
    """Archetype fetch, deck-list loading, and in-memory archetype state."""

    def fetch_archetypes(
        self,
        on_success: Callable[[list[dict[str, Any]]], None],
        on_error: Callable[[Exception], None],
        on_status: Callable[[str], None],
        force: bool = False,
    ) -> None:
        with self._loading_lock:
            if self.loading_archetypes:
                return
            self.loading_archetypes = True

        on_status("app.status.loading_archetypes_for", format=self.current_format)

        def _on_bg_refresh(fresh_archetypes: list[dict[str, Any]]) -> None:
            """Called from the repository's background thread with fresh archetype data."""
            on_success(fresh_archetypes)

        def loader(fmt: str):
            return self.metagame_repo.get_archetypes_for_format(
                fmt, force_refresh=force, on_background_refresh=_on_bg_refresh
            )

        def success_handler(archetypes: list[dict[str, Any]]):
            with self._loading_lock:
                self.loading_archetypes = False
            self.archetypes = archetypes
            self.filtered_archetypes = archetypes
            on_success(archetypes)

        def error_handler(error: Exception):
            with self._loading_lock:
                self.loading_archetypes = False
            logger.error(f"Failed to fetch archetypes: {error}")
            on_error(error)

        self._worker.submit(
            loader,
            self.current_format,
            on_success=success_handler,
            on_error=error_handler,
        )

    def load_decks(
        self,
        *,
        scope: DeckLoadScope,
        on_success: Callable[[str, list[dict[str, Any]]], None],
        on_error: Callable[[Exception], None],
        on_status: Callable[..., None],
        archetype: dict[str, Any] | None = None,
    ) -> None:
        if scope == "all":
            name = "Any"
        elif scope == "archetype" and archetype is not None:
            name = archetype.get("name", "Unknown")
        else:
            on_error(ValueError(f"Invalid deck load scope: {scope}"))
            return

        with self._loading_lock:
            if self.loading_decks:
                return
            self.loading_decks = True

        on_status("app.status.loading_decks", name=name)
        source_filter = self.get_deck_data_source()
        mtg_format = self.current_format

        def loader(_: None):
            return self.workflow_service.load_decks(
                scope=scope,
                source_filter=source_filter,
                archetype=archetype,
                mtg_format=mtg_format,
            )

        def success_handler(decks: list[dict[str, Any]]):
            with self._loading_lock:
                self.loading_decks = False
            self.workflow_service.set_decks_list(decks)
            on_success(name, decks)

        def error_handler(error: Exception):
            with self._loading_lock:
                self.loading_decks = False
            logger.error(f"Failed to load {scope} decks: {error}")
            on_error(error)

        self._worker.submit(loader, None, on_success=success_handler, on_error=error_handler)

    def get_archetypes(self) -> list[dict[str, Any]]:
        return self.archetypes

    def get_filtered_archetypes(self) -> list[dict[str, Any]]:
        return self.filtered_archetypes

    def set_filtered_archetypes(self, archetypes: list[dict[str, Any]]) -> None:
        self.filtered_archetypes = archetypes
