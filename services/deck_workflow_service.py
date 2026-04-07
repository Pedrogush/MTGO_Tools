from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from loguru import logger

from navigators.mtggoldfish import download_deck, get_archetypes
from utils.deck import read_curr_deck_file

DeckLoadScope = Literal["all", "archetype"]


class DeckWorkflowService:
    """Business logic for archetype/deck workflows, decoupled from wx UI."""

    def __init__(
        self,
        *,
        deck_repo,
        metagame_repo,
        deck_service,
        archetype_provider: Callable[..., list[dict[str, Any]]] | None = None,
        deck_downloader: Callable[[str, str | None], None] | None = None,
        deck_reader: Callable[[], str] | None = None,
    ) -> None:
        self.deck_repo = deck_repo
        self.metagame_repo = metagame_repo
        self.deck_service = deck_service
        self._archetype_provider = archetype_provider or self._default_archetype_provider
        self._deck_downloader = deck_downloader or self._default_deck_downloader
        self._deck_reader = deck_reader or read_curr_deck_file

    # ------------------------------------------------------------------ archetypes ------------------------------------------------------------------
    @staticmethod
    def _default_archetype_provider(mtg_format: str, *, allow_stale: bool) -> list[dict[str, Any]]:
        return get_archetypes(mtg_format, allow_stale=allow_stale)

    def fetch_archetypes(self, mtg_format: str, *, force: bool = False) -> list[dict[str, Any]]:
        return self._archetype_provider(mtg_format.lower(), allow_stale=not force)

    # ------------------------------------------------------------------ decks ------------------------------------------------------------------
    def load_decks(
        self,
        *,
        scope: DeckLoadScope,
        source_filter: str,
        archetype: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if scope == "all":
            return self.metagame_repo.get_all_cached_decks(source_filter=source_filter)
        if scope == "archetype":
            if archetype is None:
                raise ValueError("Archetype scope requires an archetype")
            return self.metagame_repo.get_decks_for_archetype(
                archetype, source_filter=source_filter
            )
        raise ValueError(f"Unsupported deck load scope: {scope}")

    @staticmethod
    def _default_deck_downloader(deck_number: str, source_filter: str | None = None) -> None:
        download_deck(deck_number, source_filter=source_filter)

    def download_deck_text(self, deck_number: str, *, source_filter: str | None = None) -> str:
        self._deck_downloader(deck_number, source_filter=source_filter)
        return self._deck_reader()

    def set_decks_list(self, decks: list[dict[str, Any]]) -> None:
        self.deck_repo.set_decks_list(decks)

    # ------------------------------------------------------------------ deck text helpers ------------------------------------------------------------------
    def build_deck_text(self, zone_cards: dict[str, list[dict[str, Any]]] | None = None) -> str:
        deck_text = self.deck_repo.get_current_deck_text()
        if deck_text:
            return deck_text

        zones = zone_cards if zone_cards is not None else {}
        if zones:
            try:
                deck_text = self.deck_service.build_deck_text_from_zones(zones)
            except Exception as exc:  # pragma: no cover - defensive log
                logger.debug(f"Failed to build deck text from zones: {exc}")
            else:
                if deck_text:
                    return deck_text

        current_deck = self.deck_repo.get_current_deck() or {}
        for key in ("deck_text", "content", "text"):
            value = current_deck.get(key)
            if value:
                return value

        return ""

    def save_deck(
        self,
        *,
        deck_name: str,
        deck_content: str,
        format_name: str,
        deck: dict[str, Any] | None,
        deck_save_dir,
    ) -> tuple:
        file_path = self.deck_repo.save_deck_to_file(deck_name, deck_content, deck_save_dir)

        deck_id = None
        try:
            deck_id = self.deck_repo.save_to_db(
                deck_name=deck_name,
                deck_content=deck_content,
                format_type=format_name,
                archetype=deck.get("name") if deck else None,
                player=deck.get("player") if deck else None,
                source="mtggoldfish" if deck else "manual",
                metadata=deck or {},
            )
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning(f"Deck saved to file but not database: {exc}")
        else:
            logger.info(f"Deck saved to database: {deck_name} (ID: {deck_id})")

        return file_path, deck_id

    # ------------------------------------------------------------------ averages ------------------------------------------------------------------
    def build_daily_average_buffer(
        self,
        rows: list[dict[str, Any]],
        *,
        source_filter: str,
        method: str = "karsten",
        on_progress: Callable[[int, int], None] | None = None,
    ) -> dict[str, float] | dict[str, int]:
        def progress_callback(index: int, total: int) -> None:
            if on_progress:
                on_progress(index, total)

        def download_with_filter(deck_num: str) -> None:
            self._deck_downloader(deck_num, source_filter=source_filter)

        add_func = (
            self.deck_service.add_deck_to_karsten_buffer
            if method == "karsten"
            else self.deck_service.add_deck_to_buffer
        )

        return self.deck_service.build_average_buffer(
            rows,
            download_with_filter,
            self._deck_reader,
            add_func,
            progress_callback=progress_callback,
        )
