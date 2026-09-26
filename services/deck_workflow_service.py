from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from loguru import logger

from repositories.scrapers.mtggoldfish import download_deck, get_archetypes
from services.deck_identity import DECK_ID_KEY, ensure_deck_id
from utils.deck import read_curr_deck_file

DeckLoadScope = Literal["all", "archetype"]


class DeckWorkflowService:
    """Business logic for archetype/deck workflows, decoupled from wx UI."""

    def __init__(
        self,
        *,
        deck_repo=None,
        metagame_repo=None,
        deck_service=None,
        archetype_provider: Callable[..., list[dict[str, Any]]] | None = None,
        deck_downloader: Callable[[str, str | None], None] | None = None,
        deck_reader: Callable[[], str] | None = None,
    ) -> None:
        if deck_repo is None:
            from repositories.deck_repository import get_deck_repository

            deck_repo = get_deck_repository()
        if metagame_repo is None:
            from repositories.metagame_repository import get_metagame_repository

            metagame_repo = get_metagame_repository()
        if deck_service is None:
            from services.deck_service import get_deck_service

            deck_service = get_deck_service()
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
        mtg_format: str | None = None,
    ) -> list[dict[str, Any]]:
        if scope == "all":
            return self.metagame_repo.get_all_cached_decks(
                source_filter=source_filter, mtg_format=mtg_format
            )
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

    def get_decks_list(self) -> list[dict[str, Any]]:
        return self.deck_repo.get_decks_list()

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
        file_path=None,
        archetype: str | None = None,
    ) -> tuple:
        """Write the deck file and record it in the saved-decks database.

        ``file_path`` is a path chosen in a Save As dialog and is written as-is;
        without one the deck lands in ``deck_save_dir`` under a unique name.
        ``archetype`` is the one the user assigned when saving; when it is not
        given the record falls back to the source deck's own archetype name.

        Being saved is also where a deck acquires its stable id, since this is
        where it stops being something on screen and becomes something the user
        keeps. The id is stamped on the in-memory record before anything is
        written, so the database row and the version history are keyed to the
        same deck even if one of the two writes fails.
        """
        deck_uuid = ensure_deck_id(deck)
        if file_path is not None:
            file_path = self.deck_repo.write_deck_file(file_path, deck_content)
        else:
            file_path = self.deck_repo.save_deck_to_file(deck_name, deck_content, deck_save_dir)

        if archetype is None:
            archetype = (deck or {}).get("name")
        source = (deck or {}).get("source")
        if source not in {"mtggoldfish", "mtgo", "file"}:
            # "Did this deck come from somewhere" used to be answered by whether
            # there was a record at all. A deck built here now acquires one at
            # save time, because it needs somewhere to keep its id, so the
            # question is asked of the record's contents instead: a record
            # holding nothing but that id says nothing about where the deck
            # came from, which is the same answer having no record gave.
            described_by = set(deck or {}) - {DECK_ID_KEY}
            source = "mtggoldfish" if described_by else "manual"

        deck_id = None
        try:
            deck_id = self.deck_repo.save_to_db(
                deck_name=deck_name,
                deck_content=deck_content,
                format_type=format_name,
                archetype=archetype or None,
                player=deck.get("player") if deck else None,
                source=source,
                metadata=deck or {},
                file_path=file_path,
                deck_uuid=deck_uuid or None,
            )
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning(f"Deck saved to file but not database: {exc}")
        else:
            logger.info(f"Deck saved to database: {deck_name} (ID: {deck_id})")

        self._record_version(deck, file_path, deck_content, archetype, format_name)

        return file_path, deck_id

    @staticmethod
    def _record_version(
        deck: dict[str, Any] | None,
        file_path,
        deck_content: str,
        archetype: str | None = None,
        format_name: str | None = None,
    ) -> None:
        """Commit this save into the deck's version history.

        Best effort, like the database write above it: the deck file is already
        on disk and a version-history problem must not be reported as a failed
        save. The history is a record *of* the file, never a precondition for
        writing it.

        A deck getting its history for the first time is rooted at its
        archetype's baseline when one has been computed, so that every later
        version has the archetype as an ancestor and "diff vs. baseline" needs
        no separate pointer. That root is a frozen snapshot: it is written here,
        once, and the repository layer refuses to rewrite it afterwards.

        Before either of those, a deck whose history was written under the old
        name-shaped key takes it over. This is the only place that knows both
        keys for the same deck, and it runs before the baseline seed so that an
        adopted history keeps the root it already has.

        Why a failure here is logged and not shown. The user is told at the
        moment it is actionable rather than at the moment it happens: the deck
        file is on disk and intact, and because it is now a decklist the history
        has never seen, the next time it is opened ``_check_external_edit``
        recognises it as unattributed and offers to record it. Reporting it on
        the save would interrupt a one-click action with a problem the user
        cannot act on and that the app is already going to offer to fix.
        """
        try:
            from services.deck_vcs_service import (
                adoptable_legacy_key,
                deck_key_for,
                get_deck_vcs_service,
            )

            deck_key = deck_key_for(deck, file_path)
            service = get_deck_vcs_service()
            legacy_key = adoptable_legacy_key(deck, file_path)
            if legacy_key and legacy_key != deck_key:
                service.vcs_repo.adopt_legacy_repo(deck_key, legacy_key)
            DeckWorkflowService._seed_baseline_root(deck_key, archetype, format_name)
            service.record_save(deck_key, deck_content)
        except Exception as exc:  # noqa: BLE001 - the deck file is already saved
            logger.warning(f"Deck saved but no version recorded: {exc}")

    @staticmethod
    def _seed_baseline_root(deck_key: str, archetype: str | None, format_name: str | None) -> None:
        """Root a brand-new deck's history at its archetype baseline, if any.

        Separately guarded from the save commit above it: a deck with no stored
        baseline for its archetype is an ordinary deck whose history starts at
        its first save, and that is not a failure worth surfacing.

        This runs on every save but reads the baseline store on almost none of
        them: ``seed_root_for_new_deck`` answers "does this deck already have
        history?" from the repo's refs first, and every save after a deck's
        first stops there.
        """
        if not archetype or not format_name:
            return
        try:
            from services.archetype_baseline_service import get_archetype_baseline_service

            sha = get_archetype_baseline_service().seed_root_for_new_deck(
                deck_key, archetype=archetype, mtg_format=format_name
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"No baseline root for {deck_key}: {exc}")
            return
        if sha:
            logger.info(f"Deck {deck_key} rooted at archetype baseline {sha[:7]}")

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

        return self.deck_repo.build_daily_average_deck(
            rows,
            download_with_filter,
            self._deck_reader,
            add_func,
            progress_callback=progress_callback,
        )
